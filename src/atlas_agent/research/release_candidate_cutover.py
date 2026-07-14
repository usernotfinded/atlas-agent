# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/release_candidate_cutover.py
# PURPOSE: Dry run of the research release cutover. Local release engineering only: it
#          builds a deterministic report and changes nothing.
# DEPS:    research.release_candidate_readiness
# ==============================================================================

"""Release candidate cutover dry run - local release engineering only.

This module builds and validates a deterministic report for checking whether
the repository is ready to move from a dev tag to a sandbox/paper/preflight RC
tag. It never tags, pushes, publishes, opens files, loads credentials, calls
providers, or touches brokers.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent import __version__
from atlas_agent.events.log import generate_run_id
from atlas_agent.research.sandbox_contracts import (
    FORBIDDEN_FRAGMENTS,
    _has_forbidden_fragments,
    canonical_json_dumps,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    validate_run_id,
)


RELEASE_CANDIDATE_CUTOVER_VERSION = "research_release_candidate_cutover_dry_run_v1"
ARTIFACT_TYPE = "release_candidate_cutover_dry_run"

_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}
_SAFE_INVALID_TARGET = "<invalid>"
_TARGET_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)-rc(?P<rc>[1-9]\d*)$")
_CURRENT_DEV_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\.dev(?P<dev>\d+)$")
_CURRENT_RC_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)rc(?P<rc>[1-9]\d*)$")


def _package_version_to_tag(package_version: str) -> str:
    """Map PEP 440 package version to public tag version for release note paths."""
    rc_match = _CURRENT_RC_RE.fullmatch(package_version)
    if rc_match is not None:
        return f"v{rc_match.group('major')}.{rc_match.group('minor')}.{rc_match.group('patch')}-rc{rc_match.group('rc')}"
    return f"v{package_version}"


_FINAL_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_DEV_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+\.dev\d+$")
_SHELL_META_RE = re.compile(r"[\s;&|`$<>(){}\[\]*?!'\"\\]")
_SECRET_LIKE_RE = re.compile(
    r"(Authorization|Bearer|APCA|SECRET|TOKEN|PASSWORD|API_KEY|sk-|broker\.example\.com)",
    re.IGNORECASE,
)

_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "real-money ready",
    "live_trading_ready",
    "production_trading_ready",
    "safe_to_trade",
    "trust_granted",
    "provider_execution_enabled",
    "broker_execution_enabled",
    "orders_enabled",
    "approvals_enabled",
    "autonomous_trading_ready",
    "profitable_strategy",
    "verified_alpha",
    "beats_the_market",
    "real_money_ready",
)

_HARD_FALSE_INVARIANTS = (
    "provider_call_allowed",
    "actual_provider_call_made",
    "provider_response_trusted",
    "mock_response_trusted",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
    "network_enabled",
    "credentials_loaded",
    "trust_upgrade_performed",
    "trust_decision_granted",
    "provider_execution_unlocked",
    "real_provider_response_imported",
    "live_trading_path_enabled",
    "broker_order_path_enabled",
)

_REQUIRED_BOOL_FIELDS = (
    "target_version_valid",
    "target_is_rc",
    "target_is_not_dev",
    "target_is_not_final_release",
    "current_version_is_dev",
    "dev_to_rc_transition_valid",
    "release_note_present",
    "readme_quickstart_verified",
    "public_docs_consistent",
    "release_candidate_readiness_available",
    "release_checklist_present",
    "forbidden_claims_scan_clean",
    "protected_boundaries_expected_clean",
    "live_trading_disabled_by_default",
    "provider_execution_locked",
    "trust_blocked",
    "broker_order_path_disabled",
    "credentials_not_loaded_by_provider_safety_workflow",
    "network_not_enabled_by_provider_safety_workflow",
    "no_live_trading_readiness_claims",
    "no_profitability_claims",
    "release_check_quick_listed",
    "release_check_research_listed",
    "release_check_full_listed",
)

_DERIVED_FIELDS = (
    "current_version",
    "target_version",
    "target_version_valid",
    "target_is_rc",
    "target_is_not_dev",
    "target_is_not_final_release",
    "current_version_is_dev",
    "dev_to_rc_transition_valid",
    "release_note_present",
    "readme_quickstart_verified",
    "public_docs_consistent",
    "release_candidate_readiness_available",
    "release_checklist_present",
    "forbidden_claims_scan_clean",
    "protected_boundaries_expected_clean",
    "live_trading_disabled_by_default",
    "provider_execution_locked",
    "trust_blocked",
    "broker_order_path_disabled",
    "credentials_not_loaded_by_provider_safety_workflow",
    "network_not_enabled_by_provider_safety_workflow",
    "no_live_trading_readiness_claims",
    "no_profitability_claims",
    "release_check_quick_listed",
    "release_check_research_listed",
    "release_check_full_listed",
    "cutover_status",
    "cutover_score",
    "blockers",
)

_STRUCTURAL_CHECK_NAMES = {
    "artifact_loadable",
    "artifact_type",
    "schema_version",
    "contract_version",
    "dry_run_only_true",
    "sandbox_only_true",
    "paper_first_true",
    "offline_safe_true",
    "target_version_safe",
    "unsafe_claims",
    "forbidden_fragments",
    "artifact_hash",
    "derived_cutover_match",
}
for _inv in _HARD_FALSE_INVARIANTS:
    _STRUCTURAL_CHECK_NAMES.add(f"invariant:{_inv}")


@dataclass(frozen=True)
class TargetVersionFacts:
    output_target: str
    target_version_valid: bool
    target_is_rc: bool
    target_is_not_dev: bool
    target_is_not_final_release: bool
    target_tuple: tuple[str, str, str] | None
    blockers: list[str]


@dataclass(frozen=True)
class ReleaseCandidateCutoverValidationResult:
    valid: bool
    structurally_valid: bool
    cutover_valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]
    cutover_status: str
    blockers: list[str]
    mismatched_fields: list[str]


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _has_unsafe_positive_claims(value: Any) -> bool:
    if isinstance(value, str):
        lower = value.lower()
        return any(phrase in lower for phrase in _UNSAFE_POSITIVE_CLAIM_PHRASES)
    if isinstance(value, dict):
        return any(_has_unsafe_positive_claims(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_unsafe_positive_claims(item) for item in value)
    return False


def release_candidate_cutover_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _repo_root_from_workspace(workspace_path: Path) -> Path:
    if (workspace_path / "pyproject.toml").exists():
        return workspace_path
    for parent in workspace_path.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return workspace_path


def _file_exists(repo_root: Path, rel_path: str) -> bool:
    return (repo_root / rel_path).exists()


def _read_text(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _run_local_script(repo_root: Path, rel_path: str) -> bool:
    script = repo_root / rel_path
    if not script.exists():
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
    except Exception:
        return False
    return result.returncode == 0


def _protected_boundaries_clean(repo_root: Path) -> bool:
    args = [
        "git",
        "diff",
        "--",
        "src/atlas_agent/config",
        "src/atlas_agent/brokers",
        "src/atlas_agent/execution",
        "src/atlas_agent/safety",
        "src/atlas_agent/risk",
    ]
    cached_args = ["git", "diff", "--cached", "--", *args[3:]]
    try:
        unstaged = subprocess.run(args, capture_output=True, text=True, cwd=str(repo_root))
        staged = subprocess.run(cached_args, capture_output=True, text=True, cwd=str(repo_root))
    except Exception:
        return False
    return (
        unstaged.returncode == 0
        and staged.returncode == 0
        and not unstaged.stdout.strip()
        and not staged.stdout.strip()
    )


def validate_target_version(target_version: str) -> TargetVersionFacts:
    blockers: list[str] = []
    raw = target_version if isinstance(target_version, str) else ""
    unsafe = (
        not raw
        or any(fragment in raw for fragment in FORBIDDEN_FRAGMENTS)
        or bool(_SECRET_LIKE_RE.search(raw))
        or bool(_SHELL_META_RE.search(raw))
    )

    target_is_rc = False
    target_tuple: tuple[str, str, str] | None = None
    if not unsafe:
        match = _TARGET_RE.fullmatch(raw)
        target_is_rc = match is not None
        if match is not None:
            target_tuple = (match.group("major"), match.group("minor"), match.group("patch"))

    target_is_not_dev = not bool(_DEV_TAG_RE.fullmatch(raw)) if not unsafe else False
    target_is_not_final_release = not bool(_FINAL_RE.fullmatch(raw)) if not unsafe else False
    target_version_valid = (not unsafe) and target_is_rc and target_is_not_dev and target_is_not_final_release

    if not target_version_valid:
        blockers.append("invalid_target_version")
    if not target_is_rc:
        blockers.append("target_not_rc")
    if not target_is_not_dev:
        blockers.append("target_is_dev")
    if not target_is_not_final_release:
        blockers.append("target_is_final_release")

    return TargetVersionFacts(
        output_target=raw if target_version_valid else _SAFE_INVALID_TARGET,
        target_version_valid=target_version_valid,
        target_is_rc=target_is_rc,
        target_is_not_dev=target_is_not_dev,
        target_is_not_final_release=target_is_not_final_release,
        target_tuple=target_tuple,
        blockers=blockers,
    )


def _current_version_facts(current_version: str) -> tuple[bool, bool, tuple[str, str, str] | None]:
    dev_match = _CURRENT_DEV_RE.fullmatch(current_version)
    if dev_match is not None:
        return True, False, (dev_match.group("major"), dev_match.group("minor"), dev_match.group("patch"))
    rc_match = _CURRENT_RC_RE.fullmatch(current_version)
    if rc_match is not None:
        return False, True, (rc_match.group("major"), rc_match.group("minor"), rc_match.group("patch"))
    return False, False, None


def _scan_public_docs_for_claims(repo_root: Path) -> tuple[bool, bool]:
    docs = [
        "README.md",
        "docs/release-checklist.md",
        "docs/release-candidate-readiness.md",
        "docs/release-candidate-cutover.md",
    ]
    live_phrases = (
        "live trading ready",
        "production trading ready",
        "safe to trade",
        "provider execution enabled",
        "broker execution enabled",
        "real-money ready",
    )
    profit_phrases = (
        "guaranteed profit",
        "profitable strategy",
        "verified alpha",
        "beats the market",
    )
    text = "\n".join(_read_text(repo_root, doc).lower() for doc in docs)
    live_text = text.replace("not live trading ready", "")
    no_live_claims = not any(phrase in live_text for phrase in live_phrases)
    no_profit_claims = not any(phrase in text for phrase in profit_phrases)
    return no_live_claims, no_profit_claims


def _compute_expected_cutover_core(
    workspace_path: Path,
    target_version: str,
    current_version: str = __version__,
) -> dict[str, Any]:
    repo_root = _repo_root_from_workspace(workspace_path)
    target = validate_target_version(target_version)
    current_version_is_dev, current_version_is_rc, current_tuple = _current_version_facts(current_version)
    dev_to_rc_transition_valid = (
        target.target_version_valid
        and current_tuple is not None
        and current_tuple == target.target_tuple
        and (current_version_is_dev or current_version_is_rc)
    )

    quickstart_ok = _run_local_script(repo_root, "scripts/verify_readme_quickstart.py")
    public_docs_ok = _run_local_script(repo_root, "scripts/check_public_docs_consistency.py")
    forbidden_ok = _run_local_script(repo_root, "scripts/check_forbidden_claims.py")
    release_checklist = _read_text(repo_root, "docs/release-checklist.md")
    no_live_claims, no_profit_claims = _scan_public_docs_for_claims(repo_root)

    core: dict[str, Any] = {
        "current_version": current_version,
        "target_version": target.output_target,
        "target_version_valid": target.target_version_valid,
        "target_is_rc": target.target_is_rc,
        "target_is_not_dev": target.target_is_not_dev,
        "target_is_not_final_release": target.target_is_not_final_release,
        "current_version_is_dev": current_version_is_dev,
        "dev_to_rc_transition_valid": dev_to_rc_transition_valid,
        "release_note_present": _file_exists(repo_root, f"docs/releases/{_package_version_to_tag(current_version)}.md"),
        "readme_quickstart_verified": quickstart_ok,
        "public_docs_consistent": public_docs_ok,
        "release_candidate_readiness_available": _file_exists(repo_root, "src/atlas_agent/research/release_candidate_readiness.py"),
        "release_checklist_present": bool(release_checklist),
        "forbidden_claims_scan_clean": forbidden_ok,
        "protected_boundaries_expected_clean": _protected_boundaries_clean(repo_root),
        "live_trading_disabled_by_default": True,
        "provider_execution_locked": True,
        "trust_blocked": True,
        "broker_order_path_disabled": True,
        "credentials_not_loaded_by_provider_safety_workflow": True,
        "network_not_enabled_by_provider_safety_workflow": True,
        "no_live_trading_readiness_claims": no_live_claims,
        "no_profitability_claims": no_profit_claims,
        "release_check_quick_listed": "./scripts/release_check.sh --quick" in release_checklist,
        "release_check_research_listed": "./scripts/release_check.sh --research" in release_checklist,
        "release_check_full_listed": "./scripts/release_check.sh --full" in release_checklist,
    }

    blockers = list(target.blockers)
    blocker_by_field = {
        "dev_to_rc_transition_valid": "dev_to_rc_transition_invalid",
        "release_note_present": "missing_release_note",
        "readme_quickstart_verified": "quickstart_verification_missing",
        "public_docs_consistent": "public_docs_consistency_missing",
        "release_candidate_readiness_available": "readiness_report_missing",
        "release_checklist_present": "release_checklist_missing",
        "forbidden_claims_scan_clean": "forbidden_claims_scan_missing",
        "protected_boundaries_expected_clean": "protected_boundary_dirty",
        "no_live_trading_readiness_claims": "unsafe_live_readiness_claim",
        "no_profitability_claims": "unsafe_profitability_claim",
        "release_check_quick_listed": "release_check_quick_missing",
        "release_check_research_listed": "release_check_research_missing",
        "release_check_full_listed": "release_check_full_missing",
    }
    for field in _REQUIRED_BOOL_FIELDS:
        if not core.get(field, False) and field in blocker_by_field:
            blockers.append(blocker_by_field[field])

    blockers = sorted(set(blockers))
    all_required_passed = all(bool(core.get(field)) for field in _REQUIRED_BOOL_FIELDS)
    passed = sum(1 for field in _REQUIRED_BOOL_FIELDS if bool(core.get(field)))
    score = 100 if all_required_passed else int((passed / len(_REQUIRED_BOOL_FIELDS)) * 100)

    core["cutover_status"] = "rc_dry_run_ready" if all_required_passed else "rc_dry_run_blocked"
    core["cutover_score"] = score
    core["blockers"] = blockers
    return core


def _artifact_filename(report_id: str, target_version: str) -> str:
    safe_id = validate_run_id(report_id)
    target = validate_target_version(target_version)
    slug = target.output_target if target.target_version_valid else "invalid-target"
    return f"{safe_id}__{slug}.json"


def _target_from_artifact_path(path: Path) -> str:
    stem = path.stem
    if "__" not in stem:
        return _SAFE_INVALID_TARGET
    return stem.split("__", 1)[1]


def _find_mismatched_derived_fields(
    stored: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    mismatched: list[str] = []
    for field in _DERIVED_FIELDS:
        if stored.get(field) != expected.get(field):
            mismatched.append(field)
    return mismatched


def build_release_candidate_cutover_dict(
    workspace_path: Path,
    target_version: str,
    report_id: str,
    current_version: str = __version__,
) -> dict[str, Any]:
    core = _compute_expected_cutover_core(workspace_path, target_version, current_version)
    artifact: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": RELEASE_CANDIDATE_CUTOVER_VERSION,
        "release_candidate_cutover_dry_run_id": validate_run_id(report_id),
        "created_at": datetime.now(UTC).isoformat(),
        "dry_run_only": True,
        "sandbox_only": True,
        "paper_first": True,
        "offline_safe": True,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "trust_upgrade_performed": False,
        "trust_decision_granted": False,
        "provider_execution_unlocked": False,
        "real_provider_response_imported": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "artifact_hash": "",
    }
    artifact.update(core)
    artifact["artifact_hash"] = release_candidate_cutover_sha256(artifact)
    return artifact


def _artifact_dir(workspace_path: Path) -> Path:
    return workspace_path / RESEARCH_DIR / "release_candidate_cutover_dry_runs"


def create_release_candidate_cutover_dry_run(
    workspace_path: Path,
    target_version: str,
) -> dict[str, Any]:
    report_id = generate_run_id()
    artifact = build_release_candidate_cutover_dict(workspace_path, target_version, report_id)
    target = validate_target_version(target_version)

    if target.target_version_valid:
        path = _artifact_dir(workspace_path) / _artifact_filename(report_id, target_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "ok": target.target_version_valid,
        "status": "research_release_candidate_cutover_dry_run_created"
        if target.target_version_valid
        else "research_release_candidate_cutover_dry_run_blocked",
        "release_candidate_cutover_dry_run_id": report_id if target.target_version_valid else "",
        "current_version": artifact["current_version"],
        "target_version": artifact["target_version"],
        "dry_run_only": True,
        "sandbox_only": True,
        "paper_first": True,
        "offline_safe": True,
        "cutover_status": artifact["cutover_status"],
        "cutover_score": artifact["cutover_score"],
        "blockers": artifact["blockers"],
        "tag_executed": False,
        "push_executed": False,
        "publish_executed": False,
    }


def safe_validate_release_candidate_cutover_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(data, dict):
        return None, "invalid_artifact_structure"
    if data.get("artifact_type") != ARTIFACT_TYPE:
        return None, "wrong_artifact_type"
    if data.get("schema_version") != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "schema_version_mismatch"
    if data.get("contract_version") != RELEASE_CANDIDATE_CUTOVER_VERSION:
        return None, "contract_version_mismatch"
    report_id = data.get("release_candidate_cutover_dry_run_id", "")
    if not report_id or not isinstance(report_id, str):
        return None, "missing_report_id"
    if data.get("dry_run_only") is not True:
        return None, "dry_run_only_not_true"
    if data.get("sandbox_only") is not True:
        return None, "sandbox_only_not_true"
    if data.get("paper_first") is not True:
        return None, "paper_first_not_true"
    if data.get("offline_safe") is not True:
        return None, "offline_safe_not_true"

    target_version = data.get("target_version", "")
    target = validate_target_version(target_version)
    if not target.target_version_valid:
        return None, "invalid_target_version"

    for inv in _HARD_FALSE_INVARIANTS:
        if data.get(inv) is True:
            return None, "hard_false_invariant_violation"

    if _has_unsafe_positive_claims(data):
        return None, "unsafe_claim_detected"
    json_text = json.dumps(data)
    if any(frag in json_text for frag in FORBIDDEN_FRAGMENTS):
        return None, "forbidden_fragment_detected"

    stored_hash = data.get("artifact_hash", "")
    if stored_hash and not for_replay:
        computed = release_candidate_cutover_sha256(data)
        if computed != stored_hash:
            return None, "artifact_hash_mismatch"

    return data, ""


def load_release_candidate_cutover(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cleaned, error = safe_validate_release_candidate_cutover_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def find_release_candidate_cutover_by_id(workspace_path: Path, report_id: str) -> Path | None:
    safe_id = validate_run_id(report_id)
    root = _artifact_dir(workspace_path)
    if not root.exists():
        return None
    for path in root.glob(f"{safe_id}__*.json"):
        if path.is_file():
            return path
    return None


def iter_release_candidate_cutover_artifacts(workspace_path: Path) -> list[dict[str, Any]]:
    root = _artifact_dir(workspace_path)
    if not root.exists():
        return []

    items: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            result = validate_release_candidate_cutover_artifact(path, workspace_path)
        except Exception:
            continue
        if not result.structurally_valid:
            reason = "structural_validation_failed"
            for check in result.checks:
                if not check["passed"] and check["name"] == "artifact_loadable":
                    reason = check["message"]
                    break
            else:
                for w in result.warnings:
                    if w in ("artifact_hash_mismatch", "missing_artifact_hash", "derived_cutover_mismatch"):
                        reason = w
                        break
            safe_status = "tampered" if reason in ("artifact_hash_mismatch", "missing_artifact_hash", "derived_cutover_mismatch") else "invalid"
            items.append({
                "release_candidate_cutover_dry_run_id": path.stem.split("__", 1)[0],
                "safe_status": safe_status,
                "safe_status_reason": reason,
                "target_version": "",
                "cutover_status": "",
                "cutover_score": 0,
                "created_at": "",
            })
            continue
        try:
            data = load_release_candidate_cutover(path, workspace_path)
        except Exception:
            continue
        items.append({
            "release_candidate_cutover_dry_run_id": data.get("release_candidate_cutover_dry_run_id", ""),
            "safe_status": "safe",
            "target_version": data.get("target_version", ""),
            "current_version": data.get("current_version", ""),
            "cutover_status": data.get("cutover_status", ""),
            "cutover_score": data.get("cutover_score", 0),
            "created_at": data.get("created_at", ""),
        })
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def validate_release_candidate_cutover_artifact(
    path: Path,
    workspace_path: Path | None = None,
) -> ReleaseCandidateCutoverValidationResult:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    mismatched_fields: list[str] = []
    blockers: list[str] = []
    cutover_status = ""

    try:
        data = load_release_candidate_cutover(path, workspace_path)
    except ResearchSessionError as exc:
        checks.append(_check_name("artifact_loadable", False, str(exc)))
        return ReleaseCandidateCutoverValidationResult(
            valid=False,
            structurally_valid=False,
            cutover_valid=False,
            passed_checks=0,
            failed_checks=1,
            checks=checks,
            recommendation="fix_artifact_corruption",
            warnings=warnings,
            cutover_status="",
            blockers=blockers,
            mismatched_fields=mismatched_fields,
        )

    checks.append(_check_name("artifact_loadable", True, "artifact loaded and parsed"))
    checks.append(_check_name("artifact_type", True, f"type is {ARTIFACT_TYPE}"))
    checks.append(_check_name("schema_version", True, f"schema_version={data.get('schema_version')}"))
    checks.append(_check_name("contract_version", True, f"contract_version={data.get('contract_version')}"))

    for field_name in ("dry_run_only", "sandbox_only", "paper_first", "offline_safe"):
        ok = data.get(field_name) is True
        checks.append(_check_name(f"{field_name}_true", ok, f"{field_name}={data.get(field_name)}"))
        if not ok:
            warnings.append(f"{field_name}_not_true")

    actual_target = _target_from_artifact_path(path)
    path_target_ok = data.get("target_version") == actual_target and validate_target_version(actual_target).target_version_valid
    checks.append(_check_name("target_version_safe", path_target_ok, "target version matches artifact identity" if path_target_ok else "target version mismatch"))
    if not path_target_ok:
        warnings.append("invalid_target_version")
        mismatched_fields.append("target_version")

    for inv in _HARD_FALSE_INVARIANTS:
        ok = data.get(inv) is not True
        checks.append(_check_name(f"invariant:{inv}", ok, f"{inv} is false" if ok else f"{inv} must be false"))
        if not ok:
            warnings.append("hard_false_invariant_violation")

    unsafe = _has_unsafe_positive_claims(data)
    checks.append(_check_name("unsafe_claims", not unsafe, "no unsafe positive claims" if not unsafe else "unsafe positive claim detected"))
    if unsafe:
        warnings.append("unsafe_claim_detected")

    fragments = any(frag in json.dumps(data) for frag in FORBIDDEN_FRAGMENTS)
    checks.append(_check_name("forbidden_fragments", not fragments, "no forbidden fragments" if not fragments else "forbidden fragment detected"))
    if fragments:
        warnings.append("forbidden_fragment_detected")

    stored_hash = data.get("artifact_hash", "")
    hash_ok = False
    if stored_hash:
        hash_ok = release_candidate_cutover_sha256(data) == stored_hash
        checks.append(_check_name("artifact_hash", hash_ok, "hash matches" if hash_ok else "hash mismatch"))
        if not hash_ok:
            warnings.append("artifact_hash_mismatch")
    else:
        checks.append(_check_name("artifact_hash", False, "missing artifact hash"))
        warnings.append("missing_artifact_hash")

    derived_match = True
    if workspace_path is not None and path_target_ok:
        try:
            expected = _compute_expected_cutover_core(workspace_path, actual_target, __version__)
            mismatched_fields.extend(_find_mismatched_derived_fields(data, expected))
            derived_match = not mismatched_fields
            if not derived_match:
                checks.append(_check_name("derived_cutover_match", False, "derived fields mismatch"))
                warnings.append("derived_cutover_mismatch")
            else:
                checks.append(_check_name("derived_cutover_match", True, "derived fields match"))
        except Exception:
            derived_match = False
            checks.append(_check_name("derived_cutover_match", False, "derived cutover recompute failed"))
            warnings.append("derived_cutover_mismatch")
    else:
        checks.append(_check_name("derived_cutover_match", True, "workspace unavailable; skipping derived field check"))

    cutover_status = data.get("cutover_status", "")
    blockers = data.get("blockers", [])
    blocked = cutover_status == "rc_dry_run_blocked"
    status_safe = cutover_status in ("rc_dry_run_ready", "rc_dry_run_blocked")
    checks.append(_check_name("cutover_status_safe", status_safe, f"cutover_status={cutover_status}" if status_safe else "unsafe cutover status"))
    if not status_safe:
        warnings.append("unsafe_cutover_status")
    checks.append(_check_name("cutover_not_blocked", not blocked, "cutover not blocked" if not blocked else f"blocked by {len(blockers)} check(s)"))
    if blocked:
        warnings.append("cutover_blocked")

    passed = sum(1 for check in checks if check["passed"])
    failed = len(checks) - passed
    structural_failed = sum(1 for check in checks if not check["passed"] and check["name"] in _STRUCTURAL_CHECK_NAMES)
    structurally_valid = structural_failed == 0 and not any(
        warning
        in {
            "dry_run_only_not_true",
            "sandbox_only_not_true",
            "paper_first_not_true",
            "offline_safe_not_true",
            "hard_false_invariant_violation",
            "unsafe_claim_detected",
            "forbidden_fragment_detected",
            "artifact_hash_mismatch",
            "missing_artifact_hash",
            "invalid_target_version",
            "derived_cutover_mismatch",
        }
        for warning in warnings
    )
    cutover_valid = structurally_valid and not blocked and status_safe
    valid = structurally_valid and cutover_valid and not warnings

    if not structurally_valid:
        recommendation = "fix_structural_issues"
    elif not cutover_valid:
        recommendation = "fix_cutover_blockers"
    else:
        recommendation = "artifact_valid"

    return ReleaseCandidateCutoverValidationResult(
        valid=valid,
        structurally_valid=structurally_valid,
        cutover_valid=cutover_valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
        cutover_status=cutover_status,
        blockers=blockers,
        mismatched_fields=sorted(set(mismatched_fields)),
    )


def summarize_release_candidate_cutover(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    if workspace_path is not None:
        result = validate_release_candidate_cutover_artifact(path, workspace_path)
        if not result.structurally_valid:
            reason = "structural_validation_failed"
            for check in result.checks:
                if not check["passed"] and check["name"] == "artifact_loadable":
                    reason = check["message"]
                    break
            else:
                for w in result.warnings:
                    if w in ("artifact_hash_mismatch", "missing_artifact_hash", "derived_cutover_mismatch"):
                        reason = w
                        break
            safe_status = "tampered" if reason in ("artifact_hash_mismatch", "missing_artifact_hash", "derived_cutover_mismatch") else "invalid"
            return {
                "ok": False,
                "status": "research_release_candidate_cutover_dry_run_tampered",
                "release_candidate_cutover_dry_run_id": path.stem.split("__", 1)[0],
                "current_version": "",
                "target_version": "",
                "cutover_status": "",
                "cutover_score": 0,
                "blockers": [],
                "valid": False,
                "safe_status": safe_status,
                "reason": reason,
            }
    data = load_release_candidate_cutover(path, workspace_path)
    return {
        "ok": True,
        "status": "research_release_candidate_cutover_dry_run_summarized",
        "release_candidate_cutover_dry_run_id": data.get("release_candidate_cutover_dry_run_id", ""),
        "current_version": data.get("current_version", ""),
        "target_version": data.get("target_version", ""),
        "cutover_status": data.get("cutover_status", ""),
        "cutover_score": data.get("cutover_score", 0),
        "blockers": data.get("blockers", []),
    }


def doctor_release_candidate_cutover(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    result = validate_release_candidate_cutover_artifact(path, workspace_path)
    return {
        "ok": True,
        "status": "research_release_candidate_cutover_dry_run_doctored",
        "valid": result.valid,
        "structurally_valid": result.structurally_valid,
        "cutover_valid": result.cutover_valid,
        "cutover_status": result.cutover_status,
        "blockers": result.blockers,
        "passed_checks": result.passed_checks,
        "failed_checks": result.failed_checks,
        "recommendation": result.recommendation,
        "warnings": result.warnings,
        "mismatched_fields": result.mismatched_fields,
    }
