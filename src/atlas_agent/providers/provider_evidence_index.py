"""Provider evidence index generator and inspector."""

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atlas_agent.providers.provider_preflight import (
    PreflightValidationError,
    validate_call_plan_artifact,
    verify_preflight_evidence_bundle,
)

_SECRET_FRAGMENT_RE = re.compile(
    r"(?:api[_-]?key|secret|token|password|bearer|authorization|credential)",
    re.IGNORECASE,
)

# A simple heuristic for Unix-like or Windows absolute paths
_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|[a-zA-Z]:\\)")

KNOWN_ARTIFACT_TYPES = {
    "provider_call_plan",
    "provider_preflight_validation_report",
    "provider_preflight_evidence_bundle_manifest",
    "provider_preflight_bundle_verification_report",
    "provider_preflight_smoke_report",
    "provider_readiness_report",
    "provider_capability_inventory",
}

class EvidenceIndexError(Exception):
    """Base error for evidence index failures."""
    pass


def _utc_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _is_absolute_path_string(value: str) -> bool:
    return bool(_ABSOLUTE_PATH_RE.match(value))


def _has_secret_or_absolute_values(data: Any) -> bool:
    """Recursively check for secret-like values or absolute paths in dict/list string values."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in ("notes", "root", "artifacts", "findings", "validation_errors"):
                # We still want to check the artifacts and findings, so we only skip known textual keys if it's "notes".
                # Actually, skipping "root" is correct because it's a path. Skipping "notes" is correct because it's text.
                # "validation_errors" contains text that may quote secrets if found (though we try to avoid it).
                if k.lower() in ("notes", "root", "validation_errors"):
                    continue
            if isinstance(v, str):
                if _SECRET_FRAGMENT_RE.search(v) or _is_absolute_path_string(v):
                    return True
            else:
                if _has_secret_or_absolute_values(v):
                    return True
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                if _SECRET_FRAGMENT_RE.search(item) or _is_absolute_path_string(item):
                    return True
            else:
                if _has_secret_or_absolute_values(item):
                    return True
    return False


def _is_safety_closed(data: dict[str, Any]) -> bool:
    """Returns True if all known safety fields are explicitly False (or safe)."""
    # Look for known safety fields in the artifact (typically under 'safety_flags' or 'safety_summary')
    flags_to_check = [
        "provider_enabled",
        "provider_call_made",
        "network_enabled",
        "network_used",
        "credentials_loaded",
        "credentials_allowed",
        "outbound_request_sent",
        "response_received",
        "broker_touched",
        "broker_allowed",
        "live_trading_enabled",
        "live_trading_allowed",
        "pending_order_created",
        "order_approved",
        "provider_execution_enabled",
        "provider_execution_allowed",
    ]
    
    # We walk the dict looking for these keys.
    def walk(d: Any) -> bool:
        if isinstance(d, dict):
            for k, v in d.items():
                if k in flags_to_check and v is True:
                    return False
                if not walk(v):
                    return False
        elif isinstance(d, list):
            for item in d:
                if not walk(item):
                    return False
        return True
        
    return walk(data)


def _validate_artifact(artifact: dict[str, Any], file_path: Path) -> tuple[bool, str, list[str]]:
    """Validate based on artifact type."""
    a_type = artifact.get("artifact_type")
    
    # Check for raw body fields that should be false
    minimization = artifact.get("payload_minimization_summary", {})
    if any(minimization.get(k) is True for k in ["raw_prompt_body_stored", "raw_request_body_stored", "raw_response_body_stored"]):
        return False, "invalid", ["Artifact contains raw body storage enabled"]

    if a_type == "provider_call_plan":
        try:
            validate_call_plan_artifact(artifact)
            return True, "valid", []
        except PreflightValidationError as e:
            return False, "invalid", [str(e)]
            
    elif a_type == "provider_preflight_evidence_bundle_manifest":
        # Can we verify the bundle? We need the directory.
        bundle_dir = file_path.parent
        try:
            verify_preflight_evidence_bundle(bundle_dir)
            return True, "valid", []
        except Exception as e:
            return False, "invalid", [f"Bundle verification failed: {e}"]
            
    elif a_type == "provider_preflight_smoke_report":
        if artifact.get("smoke_chain_success") is not True:
            return False, "invalid", ["Smoke chain success is not True"]
        if not _is_safety_closed(artifact):
            return False, "invalid", ["Safety flags are not closed"]
        return True, "valid", []
        
    elif a_type == "provider_readiness_report":
        if artifact.get("decision") != "preflight_only":
            return False, "invalid", ["Decision is not preflight_only"]
        if not _is_safety_closed(artifact):
            return False, "invalid", ["Safety flags are not closed"]
        return True, "valid", []
        
    elif a_type == "provider_capability_inventory":
        if not _is_safety_closed(artifact):
            return False, "invalid", ["Global safety summary is not closed"]
        return True, "valid", []
        
    # For others (validation report, bundle verification report) or unknown types, use conservative structural check
    if not _is_safety_closed(artifact):
        return False, "invalid", ["Safety flags are not closed in generic artifact"]
        
    return True, "valid", []


def build_provider_evidence_index(root: Path, output: Path | None = None) -> dict[str, Any]:
    """Scans the root for artifacts and builds an evidence index."""
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        
    MAX_DEPTH = 12
    MAX_FILES = 5000
    MAX_FILE_BYTES = 1_000_000
        
    summary = {
        "total_files_seen": 0,
        "json_files_seen": 0,
        "recognized_artifacts": 0,
        "valid_artifacts": 0,
        "invalid_artifacts": 0,
        "malformed_json_files": 0,
        "unknown_json_artifacts": 0,
        "non_json_files": 0,
        "too_large_files": 0,
        "unreadable_files": 0,
        "symlinks_skipped": 0,
    }
    
    artifacts = []
    
    output_abs = output.resolve() if output else None

    try:
        paths = sorted(root.rglob("*"))
    except RecursionError:
        raise EvidenceIndexError("RecursionError encountered during directory traversal.")
    except (OSError, PermissionError) as e:
        raise EvidenceIndexError(f"I/O Error during directory traversal: {e}")

    for path in paths:
        if summary["total_files_seen"] >= MAX_FILES:
            break

        try:
            rel_path_obj = path.relative_to(root)
            rel_path = rel_path_obj.as_posix()
            if len(rel_path_obj.parts) > MAX_DEPTH:
                continue
        except ValueError:
            continue

        if output_abs and path.resolve() == output_abs:
            continue
            
        if not path.is_file() and not path.is_symlink():
            continue
            
        summary["total_files_seen"] += 1

        if path.is_symlink():
            summary["symlinks_skipped"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "symlink_skipped",
                "sha256": None,
                "size_bytes": 0,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": ["File is a symlink"]
            })
            continue

        try:
            size_bytes = path.stat().st_size
        except (OSError, PermissionError) as e:
            summary["unreadable_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "unreadable_file",
                "sha256": None,
                "size_bytes": 0,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": [f"Cannot read file stat: {e}"]
            })
            continue

        if size_bytes > MAX_FILE_BYTES:
            summary["too_large_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "too_large",
                "sha256": None,
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": [f"File exceeds MAX_FILE_BYTES ({MAX_FILE_BYTES})"]
            })
            continue

        # Read file contents and compute hash
        try:
            content = path.read_bytes()
            file_sha256 = hashlib.sha256(content).hexdigest()
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            # Binary or non-UTF-8
            summary["non_json_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "non_json_file",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": ["File is not parseable UTF-8"]
            })
            continue
        except (OSError, PermissionError, IsADirectoryError) as e:
            summary["unreadable_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "unreadable_file",
                "sha256": None,
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": [f"Cannot read file contents: {e}"]
            })
            continue

        is_json = path.suffix.lower() == ".json"
        if not is_json:
            summary["non_json_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "non_json_file",
                "sha256": file_sha256,
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": ["File does not have .json extension"]
            })
            continue

        summary["json_files_seen"] += 1

        try:
            data = json.loads(content_str)
            parseable_json = True
        except json.JSONDecodeError:
            summary["malformed_json_files"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "malformed_json",
                "sha256": file_sha256,
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": ["Malformed JSON"]
            })
            continue

        if not isinstance(data, dict):
            summary["unknown_json_artifacts"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "unknown_json_artifact",
                "sha256": file_sha256,
                "size_bytes": size_bytes,
                "parseable_json": True,
                "recognized": False,
                "valid": False,
                "validation_status": "invalid",
                "validation_errors": ["JSON root is not an object"]
            })
            continue

        a_type = data.get("artifact_type", "unknown_json_artifact")
        recognized = a_type in KNOWN_ARTIFACT_TYPES
        if not recognized:
            summary["unknown_json_artifacts"] += 1
        else:
            summary["recognized_artifacts"] += 1

        validation_errors = []
        
        # Check raw string for secrets and absolute paths directly
        if _SECRET_FRAGMENT_RE.search(content_str) and not _has_secret_or_absolute_values(data):
             # It might be in keys, which is generally benign (e.g., "secrets_redacted": true), 
             # but we still check the parsed values.
             pass

        if _has_secret_or_absolute_values(data):
            validation_errors.append("Artifact contains secret-like values or absolute paths")

        if not _is_safety_closed(data):
            validation_errors.append("Safety flags are not closed")

        if not validation_errors and recognized:
            is_valid, status, v_errors = _validate_artifact(data, path)
            validation_errors.extend(v_errors)
        else:
            is_valid = False
            
        if validation_errors:
            is_valid = False

        status = "valid" if is_valid else "invalid"

        if is_valid:
            summary["valid_artifacts"] += 1
        else:
            summary["invalid_artifacts"] += 1

        artifacts.append({
            "relative_path": rel_path,
            "artifact_type": a_type,
            "schema_version": data.get("schema_version", 1),
            "sha256": file_sha256,
            "size_bytes": size_bytes,
            "parseable_json": True,
            "recognized": recognized,
            "valid": is_valid,
            "validation_status": status,
            "validation_errors": validation_errors,
            "safety_summary": {
                "provider_call_made": False,
                "network_used": False,
                "credentials_loaded": False,
                "broker_touched": False,
                "live_trading_enabled": False,
                "pending_order_created": False,
                "order_approved": False,
            }
        })

    index = {
        "artifact_type": "provider_evidence_index",
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "root": str(root),
        "summary": summary,
        "artifacts": artifacts,
        "findings": [a for a in artifacts if not a["valid"]],
        "safety_summary": {
            "provider_call_made": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
        }
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Avoid including any secret string in the dump. Just to be safe, we know the dict above is clean.
        output.write_text(json.dumps(index, indent=2))

    return index


def inspect_provider_evidence_index(index_path: Path) -> dict[str, Any]:
    """Inspects a previously built evidence index for validity."""
    if not index_path.exists():
        raise EvidenceIndexError("Index file does not exist.")

    try:
        content_str = index_path.read_text(encoding="utf-8")
        data = json.loads(content_str)
    except Exception as e:
        raise EvidenceIndexError(f"Index is not parseable JSON: {e}")

    if data.get("artifact_type") != "provider_evidence_index":
        raise EvidenceIndexError("Not a provider_evidence_index artifact.")

    if data.get("schema_version") != 1:
        raise EvidenceIndexError("Unsupported schema_version.")

    required_fields = ["generated_at", "root", "summary", "artifacts", "findings", "safety_summary"]
    for f in required_fields:
        if f not in data:
            raise EvidenceIndexError(f"Missing required field: {f}")

    if _has_secret_or_absolute_values(data):
        raise EvidenceIndexError("Index contains secret-like values or absolute paths.")

    if not _is_safety_closed(data):
        raise EvidenceIndexError("Index safety summary is not closed.")

    return data
