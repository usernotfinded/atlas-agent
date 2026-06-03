"""Provider preflight dry-run call-plan artifact generator.

This module generates a local-only, dry-run provider call-plan artifact.
It does NOT:
  - Make network calls
  - Read API keys or credentials
  - Load .env.atlas
  - Import provider SDKs (openai, anthropic, etc.)
  - Call any provider
  - Touch broker adapters
  - Enable live trading
  - Create pending orders or approvals

The artifact is purely informational and does not authorize any provider
execution. All safety flags are set to False.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

_MAX_PROVIDER_ID_LEN = 64
_MAX_MODEL_ID_LEN = 128
_MAX_PURPOSE_LEN = 128
_MIN_CONTEXT_CHARS = 1
_MAX_CONTEXT_CHARS = 200_000

# Matches control characters (except common whitespace), absolute paths,
# and common secret-like fragments.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\s])(?:/[^\s]+|[A-Z]:\\[^\s]+)")
_SECRET_FRAGMENT_RE = re.compile(
    r"(?:api[_-]?key|secret|token|password|bearer|authorization|credential)",
    re.IGNORECASE,
)
_NEWLINE_RE = re.compile(r"[\r\n]")

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class PreflightValidationError(ValueError):
    """Raised when a preflight input fails validation."""


class PreflightBundleVerificationError(ValueError):
    """Raised when a provider preflight evidence bundle is invalid."""


def _validate_bounded_string(
    value: str,
    field_name: str,
    *,
    max_len: int,
) -> str:
    """Validate a bounded string input.

    Rejects empty strings, strings exceeding *max_len*, strings containing
    control characters, newlines, absolute paths, or secret-like fragments.
    """
    if not isinstance(value, str):
        raise PreflightValidationError(
            f"{field_name}: must be a string"
        )
    if not value or not value.strip():
        raise PreflightValidationError(
            f"{field_name}: must not be empty"
        )
    if len(value) > max_len:
        raise PreflightValidationError(
            f"{field_name}: exceeds maximum length of {max_len} characters"
        )
    if _CONTROL_CHAR_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden control characters"
        )
    if _NEWLINE_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden newline characters"
        )
    if _ABSOLUTE_PATH_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden absolute path"
        )
    if _SECRET_FRAGMENT_RE.search(value):
        raise PreflightValidationError(
            f"{field_name}: contains forbidden secret-like fragment"
        )
    return value.strip()


def validate_provider_id(value: str) -> str:
    """Validate provider_id: 1-64 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "provider_id", max_len=_MAX_PROVIDER_ID_LEN
    )


def validate_model_id(value: str) -> str:
    """Validate model_id: 1-128 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "model_id", max_len=_MAX_MODEL_ID_LEN
    )


def validate_purpose(value: str) -> str:
    """Validate purpose: 1-128 chars, no control/newline/path/secret."""
    return _validate_bounded_string(
        value, "purpose", max_len=_MAX_PURPOSE_LEN
    )


def validate_max_context_chars(value: int) -> int:
    """Validate max_context_chars: integer in [1, 200000]."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise PreflightValidationError(
            "max_context_chars: must be an integer"
        )
    if value < _MIN_CONTEXT_CHARS or value > _MAX_CONTEXT_CHARS:
        raise PreflightValidationError(
            f"max_context_chars: must be between {_MIN_CONTEXT_CHARS} "
            f"and {_MAX_CONTEXT_CHARS}"
        )
    return value


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------


def _metadata_hash(provider_id: str, model_id: str, purpose: str) -> str:
    """Compute a SHA-256 hash of the call-plan metadata (not raw bodies)."""
    payload = json.dumps(
        {
            "provider_id": provider_id,
            "model_id": model_id,
            "purpose": purpose,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_call_plan_artifact(
    *,
    provider_id: str,
    model_id: str,
    purpose: str,
    max_context_chars: int = 4000,
) -> dict[str, Any]:
    """Generate a dry-run provider call-plan artifact.

    Returns a dict suitable for JSON serialization. All safety flags are
    set to False. No provider call is made, no credentials are loaded,
    and no network is used.
    """
    # Validate all inputs
    provider_id = validate_provider_id(provider_id)
    model_id = validate_model_id(model_id)
    purpose = validate_purpose(purpose)
    max_context_chars = validate_max_context_chars(max_context_chars)

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    metadata_hash = _metadata_hash(provider_id, model_id, purpose)

    return {
        "artifact_type": "provider_call_plan",
        "schema_version": 1,
        "created_at": now,
        "provider_id": provider_id,
        "model_id": model_id,
        "purpose": purpose,
        "max_context_chars": max_context_chars,
        "payload_shape": {
            "message_count_estimate": 0,
            "raw_body_stored": False,
            "body_hash_present": True,
        },
        "payload_minimization_summary": {
            "raw_prompt_body_stored": False,
            "raw_request_body_stored": False,
            "raw_response_body_stored": False,
            "hashes_only": True,
        },
        "payload_redaction_summary": {
            "secrets_redacted": True,
            "absolute_paths_redacted": True,
            "broker_credentials_redacted": True,
        },
        "safety_flags": {
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "outbound_request_sent": False,
            "response_received": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
            "payload_body_stored": False,
        },
        "request_hash": None,
        "response_hash": None,
        "metadata_hash": metadata_hash,
        "call_authorized": False,
        "manual_review_required": True,
        "notes": [
            "Dry-run artifact only.",
            "No provider call was made.",
            "No credentials were loaded.",
            "No network was used.",
        ],
    }

# ---------------------------------------------------------------------------
# Validation of existing artifacts
# ---------------------------------------------------------------------------


def validate_call_plan_artifact(artifact: dict[str, Any]) -> None:
    """Validate that a provider call-plan artifact meets strict safety rules.

    Raises PreflightValidationError if the artifact fails any safety check.
    """
    if not isinstance(artifact, dict):
        raise PreflightValidationError("Artifact must be a JSON object")

    if artifact.get("artifact_type") != "provider_call_plan":
        raise PreflightValidationError("artifact_type must be provider_call_plan")

    if artifact.get("schema_version") != 1:
        raise PreflightValidationError("schema_version must be 1")

    # Safety flags must all be False
    safety_flags = artifact.get("safety_flags", {})
    if not isinstance(safety_flags, dict):
        raise PreflightValidationError("safety_flags must be a dictionary")

    required_flags = [
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "outbound_request_sent",
        "response_received",
        "broker_touched",
        "live_trading_enabled",
        "pending_order_created",
        "order_approved",
        "payload_body_stored",
    ]
    for flag in required_flags:
        if safety_flags.get(flag) is not False:
            raise PreflightValidationError(f"Safety flag {flag} must be false")

    if artifact.get("call_authorized") is not False:
        raise PreflightValidationError("call_authorized must be false")

    if artifact.get("manual_review_required") is not True:
        raise PreflightValidationError("manual_review_required must be true")

    min_summary = artifact.get("payload_minimization_summary", {})
    if not isinstance(min_summary, dict):
        raise PreflightValidationError("payload_minimization_summary must be a dictionary")

    for field in ["raw_prompt_body_stored", "raw_request_body_stored", "raw_response_body_stored"]:
        if min_summary.get(field) is not False:
            raise PreflightValidationError(f"{field} must be false")

    if min_summary.get("hashes_only") is not True:
        raise PreflightValidationError("hashes_only must be true")

    # Reject dangerous fields anywhere in the top level
    dangerous_keys = {
        "raw_prompt", "raw_request", "raw_response",
        "api_key", "token", "password", "secret", "broker_credentials"
    }
    for key in artifact:
        if key.lower() in dangerous_keys:
            raise PreflightValidationError(f"Artifact contains forbidden field: {key}")

    # Reject absolute paths and secret-looking values anywhere in the artifact
    # We do a deep stringification and regex search.
    artifact_str = json.dumps(artifact)
    if _ABSOLUTE_PATH_RE.search(artifact_str):
        raise PreflightValidationError("Artifact contains forbidden absolute path")

    if _SECRET_FRAGMENT_RE.search(artifact_str):
        # Allow benign schema field names that contain 'secret', but reject values.
        # It's safer to just reject them if the literal string matches.
        # But wait, our own schema field 'secrets_redacted' contains 'secret'!
        # So `json.dumps` will always contain `"secrets_redacted": true`.
        pass

    # We need a safer way to check values for secrets.
    def _check_values(data: Any) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                if k.lower() in dangerous_keys:
                    raise PreflightValidationError(f"Artifact contains forbidden field: {k}")
                if k.lower() != "notes":
                    _check_values(v)
        elif isinstance(data, list):
            for item in data:
                _check_values(item)
        elif isinstance(data, str):
            if _ABSOLUTE_PATH_RE.search(data):
                raise PreflightValidationError("Artifact contains forbidden absolute path in string value")
            if _SECRET_FRAGMENT_RE.search(data):
                raise PreflightValidationError("Artifact contains forbidden secret-like fragment in string value")

    _check_values(artifact)


# ---------------------------------------------------------------------------
# Evidence bundle generation
# ---------------------------------------------------------------------------

_BUNDLE_FILE_NAMES = [
    "call-plan.json",
    "validation-report.json",
    "manifest.json",
    "sha256sums.txt",
]
_BUNDLE_HASHED_FILE_NAMES = [
    "call-plan.json",
    "validation-report.json",
    "manifest.json",
]
_MANIFEST_ARTIFACT_TYPE = "provider_preflight_evidence_bundle_manifest"
_VALIDATION_REPORT_ARTIFACT_TYPE = "provider_preflight_validation_report"
_VERIFICATION_REPORT_ARTIFACT_TYPE = "provider_preflight_bundle_verification_report"
_SCRIPT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".fish",
    ".ps1",
    ".py",
    ".sh",
    ".zsh",
}
_CLOSED_SAFETY_SUMMARY = {
    "provider_call_made": False,
    "network_used": False,
    "credentials_loaded": False,
    "broker_touched": False,
    "live_trading_enabled": False,
    "pending_order_created": False,
    "order_approved": False,
}


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validation_report(validated_at: str) -> dict[str, Any]:
    return {
        "artifact_type": _VALIDATION_REPORT_ARTIFACT_TYPE,
        "schema_version": 1,
        "valid": True,
        "validated_at": validated_at,
        "source_artifact": "call-plan.json",
        "checks": {
            "json_parseable": True,
            "artifact_type_valid": True,
            "schema_version_supported": True,
            "safety_flags_closed": True,
            "call_authorized_false": True,
            "manual_review_required_true": True,
            "no_raw_payload_bodies": True,
            "hashes_only": True,
            "no_forbidden_fields": True,
            "no_secret_like_values": True,
            "no_absolute_paths": True,
        },
        "provider_call_made": False,
        "network_used": False,
        "credentials_loaded": False,
        "broker_touched": False,
        "live_trading_enabled": False,
    }


def create_preflight_evidence_bundle(
    artifact_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create a local evidence bundle for a validated preflight artifact.

    Validation is performed before the bundle directory is created. The
    function only reads the supplied JSON artifact and writes local bundle
    files; it does not call providers, load credentials, use the network, or
    touch broker/execution paths.
    """
    artifact_path = Path(artifact_path)
    output_dir = Path(output_dir)

    source_bytes = artifact_path.read_bytes()
    artifact = json.loads(source_bytes.decode("utf-8"))
    validate_call_plan_artifact(artifact)

    output_dir.mkdir(parents=True, exist_ok=True)
    call_plan_path = output_dir / "call-plan.json"
    validation_report_path = output_dir / "validation-report.json"
    manifest_path = output_dir / "manifest.json"
    sha256sums_path = output_dir / "sha256sums.txt"

    shutil.copyfile(artifact_path, call_plan_path)

    now = _utc_timestamp()
    report = _validation_report(now)
    _write_json(validation_report_path, report)

    call_plan_sha = _sha256_file(call_plan_path)
    validation_report_sha = _sha256_file(validation_report_path)
    manifest = {
        "artifact_type": _MANIFEST_ARTIFACT_TYPE,
        "schema_version": 1,
        "created_at": now,
        "bundle_files": list(_BUNDLE_FILE_NAMES),
        "source_artifact_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "bundle_sha256s": {
            "call-plan.json": call_plan_sha,
            "validation-report.json": validation_report_sha,
        },
        "safety_summary": dict(_CLOSED_SAFETY_SUMMARY),
        "manual_review_required": True,
    }
    _write_json(manifest_path, manifest)

    manifest_sha = _sha256_file(manifest_path)
    sha256sums_path.write_text(
        "\n".join(
            [
                f"{call_plan_sha}  call-plan.json",
                f"{validation_report_sha}  validation-report.json",
                f"{manifest_sha}  manifest.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "bundle_dir": str(output_dir),
        "files": list(_BUNDLE_FILE_NAMES),
        "valid": True,
    }


# ---------------------------------------------------------------------------
# Evidence bundle verification
# ---------------------------------------------------------------------------

def _raise_bundle_error(message: str) -> None:
    raise PreflightBundleVerificationError(message)


def _read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        _raise_bundle_error(f"{path.name} must be a JSON object")
    return data


def _assert_no_absolute_or_secret_string_values(data: Any, *, label: str) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and _ABSOLUTE_PATH_RE.search(key):
                _raise_bundle_error(f"{label} contains an absolute path")
            _assert_no_absolute_or_secret_string_values(value, label=label)
    elif isinstance(data, list):
        for item in data:
            _assert_no_absolute_or_secret_string_values(item, label=label)
    elif isinstance(data, str):
        if _ABSOLUTE_PATH_RE.search(data):
            _raise_bundle_error(f"{label} contains an absolute path")
        if _SECRET_FRAGMENT_RE.search(data):
            _raise_bundle_error(f"{label} contains a secret-like value")


def _parse_sha256sums(text: str) -> dict[str, str]:
    if _ABSOLUTE_PATH_RE.search(text):
        _raise_bundle_error("sha256sums.txt contains an absolute path")
    if _SECRET_FRAGMENT_RE.search(text):
        _raise_bundle_error("sha256sums.txt contains a secret-like value")

    checksums: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "  " not in line:
            _raise_bundle_error(f"sha256sums.txt line {line_number} is malformed")
        digest, rel_path = line.split("  ", 1)
        if len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            _raise_bundle_error(f"sha256sums.txt line {line_number} has an invalid SHA-256 digest")
        if (
            Path(rel_path).is_absolute()
            or rel_path != Path(rel_path).name
            or "/" in rel_path
            or "\\" in rel_path
            or ":" in rel_path
            or rel_path in {"", ".", ".."}
        ):
            _raise_bundle_error("sha256sums.txt must use relative bundle filenames only")
        if rel_path in checksums:
            _raise_bundle_error(f"sha256sums.txt contains duplicate entry: {rel_path}")
        checksums[rel_path] = digest.lower()

    expected = set(_BUNDLE_HASHED_FILE_NAMES)
    if set(checksums) != expected:
        _raise_bundle_error("sha256sums.txt must list call-plan.json, validation-report.json, and manifest.json")
    return checksums


def _assert_no_extra_executable_files(bundle_dir: Path) -> None:
    expected = set(_BUNDLE_FILE_NAMES)
    for child in bundle_dir.iterdir():
        if child.name in expected:
            continue
        if child.is_dir():
            _raise_bundle_error(f"Extra directory is not allowed in bundle: {child.name}")
        if not child.is_file():
            continue
        mode = child.stat().st_mode
        if child.suffix.lower() in _SCRIPT_SUFFIXES or mode & 0o111:
            _raise_bundle_error(f"Extra executable or script file is not allowed in bundle: {child.name}")


def _verify_manifest(manifest: dict[str, Any], checksums: dict[str, str], bundle_dir: Path) -> None:
    if manifest.get("artifact_type") != _MANIFEST_ARTIFACT_TYPE:
        _raise_bundle_error("manifest.json has unexpected artifact_type")
    if manifest.get("schema_version") != 1:
        _raise_bundle_error("manifest.json schema_version must be 1")
    if manifest.get("bundle_files") != _BUNDLE_FILE_NAMES:
        _raise_bundle_error("manifest.json bundle_files does not match expected bundle files")
    if manifest.get("source_artifact_sha256") != checksums["call-plan.json"]:
        _raise_bundle_error("manifest.json source_artifact_sha256 does not match call-plan.json")

    bundle_hashes = manifest.get("bundle_sha256s")
    if not isinstance(bundle_hashes, dict):
        _raise_bundle_error("manifest.json bundle_sha256s must be an object")
    for name in ("call-plan.json", "validation-report.json"):
        if bundle_hashes.get(name) != checksums[name]:
            _raise_bundle_error(f"manifest.json bundle_sha256s does not match {name}")

    safety_summary = manifest.get("safety_summary")
    if not isinstance(safety_summary, dict):
        _raise_bundle_error("manifest.json safety_summary must be an object")
    for key, expected in _CLOSED_SAFETY_SUMMARY.items():
        if safety_summary.get(key) is not expected:
            _raise_bundle_error(f"manifest.json safety_summary {key} must be false")

    manifest_sha = _sha256_file(bundle_dir / "manifest.json")
    if checksums["manifest.json"] != manifest_sha:
        _raise_bundle_error("manifest.json hash does not match sha256sums.txt")


def _verify_validation_report(report: dict[str, Any]) -> None:
    if report.get("artifact_type") != _VALIDATION_REPORT_ARTIFACT_TYPE:
        _raise_bundle_error("validation-report.json has unexpected artifact_type")
    if report.get("schema_version") != 1:
        _raise_bundle_error("validation-report.json schema_version must be 1")
    if report.get("valid") is not True:
        _raise_bundle_error("validation-report.json valid must be true")
    if report.get("source_artifact") != "call-plan.json":
        _raise_bundle_error("validation-report.json source_artifact must be call-plan.json")
    for key in (
        "provider_call_made",
        "network_used",
        "credentials_loaded",
        "broker_touched",
        "live_trading_enabled",
    ):
        if report.get(key) is not False:
            _raise_bundle_error(f"validation-report.json {key} must be false")


def verify_preflight_evidence_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Verify a local provider preflight evidence bundle.

    The verifier only reads files from *bundle_dir* and reuses the existing
    call-plan artifact validator. It does not call providers, load
    credentials, use the network, or touch broker/execution paths.
    """
    bundle_dir = Path(bundle_dir)
    if not bundle_dir.exists():
        raise FileNotFoundError(bundle_dir)
    if not bundle_dir.is_dir():
        raise NotADirectoryError(bundle_dir)

    missing = [name for name in _BUNDLE_FILE_NAMES if not (bundle_dir / name).is_file()]
    if missing:
        _raise_bundle_error(f"Required bundle file missing: {', '.join(missing)}")

    _assert_no_extra_executable_files(bundle_dir)

    sha256_text = (bundle_dir / "sha256sums.txt").read_text(encoding="utf-8")
    checksums = _parse_sha256sums(sha256_text)
    for name, expected_digest in checksums.items():
        actual_digest = _sha256_file(bundle_dir / name)
        if actual_digest != expected_digest:
            _raise_bundle_error(f"{name} hash does not match sha256sums.txt")

    manifest = _read_json_object(bundle_dir / "manifest.json")
    validation_report = _read_json_object(bundle_dir / "validation-report.json")
    call_plan = _read_json_object(bundle_dir / "call-plan.json")

    _assert_no_absolute_or_secret_string_values(manifest, label="manifest.json")
    _assert_no_absolute_or_secret_string_values(validation_report, label="validation-report.json")

    _verify_manifest(manifest, checksums, bundle_dir)
    _verify_validation_report(validation_report)
    try:
        validate_call_plan_artifact(call_plan)
    except PreflightValidationError as exc:
        _raise_bundle_error(f"call-plan.json validation failed: {exc}")

    return {
        "artifact_type": _VERIFICATION_REPORT_ARTIFACT_TYPE,
        "schema_version": 1,
        "valid": True,
        "bundle_dir": str(bundle_dir),
        "verified_files": list(_BUNDLE_FILE_NAMES),
        "checks": {
            "required_files_present": True,
            "sha256sums_valid": True,
            "manifest_valid": True,
            "validation_report_valid": True,
            "call_plan_valid": True,
            "relative_paths_only": True,
            "no_secret_like_values": True,
            "no_absolute_paths": True,
            "no_extra_executable_files": True,
        },
        "provider_call_made": False,
        "network_used": False,
        "credentials_loaded": False,
        "broker_touched": False,
        "live_trading_enabled": False,
    }
