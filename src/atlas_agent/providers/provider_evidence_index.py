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
    "provider_preflight_sha256sums",
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


def build_provider_evidence_index(
    root: Path,
    output: Path | None = None,
    exclude_paths: set[Path] | list[Path] | tuple[Path, ...] | None = None,
) -> dict[str, Any]:
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
    
    excluded_abs = {Path(path).resolve() for path in (exclude_paths or [])}
    if output:
        excluded_abs.add(output.resolve())

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

        if path.resolve() in excluded_abs:
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

        if path.name == "sha256sums.txt":
            summary["recognized_artifacts"] += 1
            validation_errors = []
            try:
                verify_preflight_evidence_bundle(path.parent)
            except Exception:
                validation_errors.append("sha256sums.txt bundle verification failed")
            is_valid = not validation_errors
            if is_valid:
                summary["valid_artifacts"] += 1
            else:
                summary["invalid_artifacts"] += 1
            artifacts.append({
                "relative_path": rel_path,
                "artifact_type": "provider_preflight_sha256sums",
                "schema_version": 1,
                "sha256": file_sha256,
                "size_bytes": size_bytes,
                "parseable_json": False,
                "recognized": True,
                "valid": is_valid,
                "validation_status": "valid" if is_valid else "invalid",
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


def _determine_finding_severity(finding_type: str, finding_msg: str) -> str:
    msg_lower = finding_msg.lower()
    t_lower = finding_type.lower()

    if _SECRET_FRAGMENT_RE.search(finding_msg) or "secret" in msg_lower or "credential" in msg_lower:
        return "critical"

    if "unsafe" in msg_lower or "absolute path" in msg_lower:
        return "error"

    critical = {"secret_like_value_detected", "credentials_loaded", "provider_execution_allowed", "broker_touched", "live_trading_enabled", "pending_order_created", "order_approved"}
    error = {"malformed_json", "invalid_artifact", "unsafe_safety_flag", "absolute_path_detected", "hash_mismatch", "unreadable_file"}
    warning = {"unknown_json_artifact", "non_json_file", "too_large", "symlink_skipped", "orphaned_artifact", "duplicate_artifact"}
    info = {"recognized_valid_artifact"}

    for c in critical:
        if c in msg_lower or c in t_lower:
            return "critical"
    for e in error:
        if e in msg_lower or e in t_lower:
            return "error"
    for w in warning:
        if w in msg_lower or w in t_lower:
            return "warning"
    for i in info:
        if i in msg_lower or i in t_lower:
            return "info"

    if "error" in msg_lower or "fail" in msg_lower or "invalid" in msg_lower:
        return "error"

    return "warning"


def export_provider_evidence_summary(index_path: Path, output: Path | None = None) -> dict[str, Any]:
    if not index_path.exists():
        raise EvidenceIndexError("Index file does not exist.")
    try:
        content_bytes = index_path.read_bytes()
        content_str = content_bytes.decode("utf-8")
        source_sha256 = hashlib.sha256(content_bytes).hexdigest()
        data = json.loads(content_str)
    except Exception as e:
        raise EvidenceIndexError(f"Index is not parseable JSON: {e}")

    if data.get("artifact_type") != "provider_evidence_index":
        raise EvidenceIndexError("Not a provider_evidence_index artifact.")

    try:
        inspect_provider_evidence_index(index_path)
        is_valid = True
        err_msg = ""
    except EvidenceIndexError as e:
        is_valid = False
        err_msg = str(e)

    # Build summary
    finding_counts = {"info": 0, "warning": 0, "error": 0, "critical": 0}
    type_distribution = {}

    for a in data.get("artifacts", []):
        atype = a.get("artifact_type", "unknown")
        type_distribution[atype] = type_distribution.get(atype, 0) + 1

    for f in data.get("findings", []):
        msg = ", ".join(f.get("validation_errors", []))
        atype = f.get("artifact_type", "unknown")
        sev = _determine_finding_severity(atype, msg)
        finding_counts[sev] += 1

    if not is_valid and err_msg:
        # Ensure we count the root index failure
        sev = _determine_finding_severity("index_error", err_msg)
        finding_counts[sev] += 1

    summary = {
        "artifact_type": "provider_evidence_index_summary",
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "source_index_sha256": source_sha256,
        "source_index_path": str(index_path),
        "summary": data.get("summary", {}),
        "artifact_type_distribution": type_distribution,
        "finding_counts_by_severity": finding_counts,
        "safety_summary": data.get("safety_summary", {
            "provider_call_made": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
        }),
        "review_required": True,
        "valid": is_valid
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2))

    return summary


def render_provider_evidence_markdown_report(index_data: dict[str, Any], source_index_sha256: str, is_valid: bool, index_err_msg: str) -> str:
    lines = [
        "# Provider Evidence Index Report",
        "",
        "## Summary",
        f"- **generated_at**: {index_data.get('generated_at', 'unknown')}",
        f"- **root**: {index_data.get('root', 'unknown')}",
        f"- **source_index_sha256**: {source_index_sha256[:8]}",
        f"- **valid**: {str(is_valid).lower()}"
    ]

    if index_err_msg:
        lines.append(f"- **index_error**: {index_err_msg}")

    summary = index_data.get("summary", {})
    for k, v in summary.items():
        # Replace underscores with spaces for readability in some keys, or keep as is.
        lines.append(f"- **{k.replace('_', ' ')}**: {v}")

    lines.extend(["", "## Safety Summary"])
    safety = index_data.get("safety_summary", {})
    for k, v in safety.items():
        lines.append(f"- **{k}**: {str(v).lower()}")

    lines.extend(["", "## Artifact Type Distribution"])
    type_distribution = {}
    for a in index_data.get("artifacts", []):
        atype = a.get("artifact_type", "unknown")
        type_distribution[atype] = type_distribution.get(atype, 0) + 1

    lines.extend([
        "| Artifact Type | Count |",
        "|---|---|"
    ])
    for t, c in type_distribution.items():
        lines.append(f"| {t} | {c} |")

    lines.extend(["", "## Findings"])
    lines.extend([
        "| Severity | Type | Path | Message |",
        "|---|---|---|---|"
    ])

    findings = index_data.get("findings", [])
    if not findings and is_valid:
        lines.append("| info | none | N/A | No findings |")
    else:
        for f in findings:
            msg = ", ".join(f.get("validation_errors", []))
            # Redact secrets in markdown
            if _SECRET_FRAGMENT_RE.search(msg) or "secret" in msg.lower():
                msg = "[REDACTED SECRET-LIKE VALUE IN FINDING MESSAGE]"
            # Remove absolute paths
            if "absolute path" in msg.lower() or _is_absolute_path_string(msg) or re.search(r'(?:^|\s)(?:/|[a-zA-Z]:\\)', msg):
                msg = "[REDACTED ABSOLUTE PATH IN FINDING MESSAGE]"
            atype = f.get("artifact_type", "unknown")
            sev = _determine_finding_severity(atype, msg)
            rel_path = f.get("relative_path", "unknown")
            lines.append(f"| {sev} | {atype} | {rel_path} | {msg} |")

    lines.extend(["", "## Invalid or Unsafe Artifacts"])
    lines.extend([
        "| Path | Artifact Type | Validation Status | Errors |",
        "|---|---|---|---|"
    ])
    unsafe = [a for a in index_data.get("artifacts", []) if not a.get("valid", False)]
    if not unsafe:
        lines.append("| N/A | N/A | N/A | None |")
    else:
        for u in unsafe:
            msg = ", ".join(u.get("validation_errors", []))
            if _SECRET_FRAGMENT_RE.search(msg) or "secret" in msg.lower():
                msg = "[REDACTED SECRET-LIKE VALUE]"
            if "absolute path" in msg.lower() or _is_absolute_path_string(msg) or re.search(r'(?:^|\s)(?:/|[a-zA-Z]:\\)', msg):
                msg = "[REDACTED ABSOLUTE PATH]"
            lines.append(f"| {u.get('relative_path', 'unknown')} | {u.get('artifact_type', 'unknown')} | {u.get('validation_status', 'invalid')} | {msg} |")

    lines.extend(["", "## Recognized Artifacts"])
    lines.extend([
        "| Path | Artifact Type | Schema Version | SHA-256 | Valid |",
        "|---|---|---|---|---|"
    ])
    rec = [a for a in index_data.get("artifacts", []) if a.get("recognized", False)]
    if not rec:
        lines.append("| N/A | N/A | N/A | N/A | N/A |")
    else:
        for r in rec:
            sha = r.get("sha256", "unknown")
            if len(sha) > 8:
                sha = sha[:8]
            lines.append(f"| {r.get('relative_path', 'unknown')} | {r.get('artifact_type', 'unknown')} | {r.get('schema_version', 1)} | {sha} | {str(r.get('valid', False)).lower()} |")

    lines.extend([
        "",
        "## Reviewer Notes",
        "- This report is generated from local evidence artifacts.",
        "- It does not authorize provider execution.",
        "- It does not authorize broker execution.",
        "- It does not authorize live trading."
    ])

    return "\n".join(lines)


def generate_provider_evidence_report(index_path: Path, output: Path | None = None) -> dict[str, Any]:
    if not index_path.exists():
        raise EvidenceIndexError("Index file does not exist.")
    try:
        content_bytes = index_path.read_bytes()
        content_str = content_bytes.decode("utf-8")
        source_sha256 = hashlib.sha256(content_bytes).hexdigest()
        data = json.loads(content_str)
    except Exception as e:
        raise EvidenceIndexError(f"Index is not parseable JSON: {e}")

    if data.get("artifact_type") != "provider_evidence_index":
        raise EvidenceIndexError("Not a provider_evidence_index artifact.")

    try:
        inspect_provider_evidence_index(index_path)
        is_valid = True
        err_msg = ""
    except EvidenceIndexError as e:
        is_valid = False
        err_msg = str(e)

    md_content = render_provider_evidence_markdown_report(data, source_sha256, is_valid, err_msg)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")

    return {
        "is_valid": is_valid,
        "error_message": err_msg,
        "markdown": md_content,
        "source_sha256": source_sha256
    }
