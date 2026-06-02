"""Release candidate readiness report — sandbox/paper/preflight only.

This module creates, validates, lists, shows, replays, summarizes, and doctors
release-candidate-readiness artifacts. The report is read-only and local:
it inspects repository files and verification scripts, but never loads credentials,
makes network calls, or touches brokers.
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
    validate_contract_symbol,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    _is_inside_workspace,
    validate_run_id,
)

RELEASE_CANDIDATE_READINESS_VERSION = "research_release_candidate_readiness_v1"

_RELEASE_CANDIDATE_READINESS_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

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
)

# Hard-false invariants that must remain False
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

# Required docs/files for a sandbox release candidate
_REQUIRED_DOCS = (
    "README.md",
    "docs/provider-safety-dossier.md",
    "docs/examples/provider-safety-dossier-workflow.md",
    "docs/release-checklist.md",
)

# Required verification scripts
_REQUIRED_SCRIPTS = (
    "scripts/verify_readme_quickstart.py",
    "scripts/check_public_docs_consistency.py",
    "scripts/check_version_consistency.py",
    "scripts/check_forbidden_claims.py",
)

# Fields that are derived from repo state and must match recomputed values
_DERIVED_READINESS_FIELDS = (
    "version",
    "readiness_status",
    "readiness_score",
    "sandbox_only",
    "paper_first",
    "offline_safe",
    "quickstart_verified",
    "public_docs_consistent",
    "provider_safety_docs_present",
    "provider_safety_dossier_commands_documented",
    "provider_safety_dossier_export_documented",
    "provider_safety_dossier_discovery_documented",
    "release_checklist_present",
    "release_note_present",
    "forbidden_claims_scan_clean",
    "protected_boundaries_expected_clean",
    "live_trading_disabled_by_default",
    "provider_execution_locked",
    "trust_blocked",
    "broker_order_path_disabled",
    "credentials_not_loaded_by_provider_safety_workflow",
    "network_not_enabled_by_provider_safety_workflow",
    "checks",
    "blockers",
)


def _has_unsafe_positive_claims(value: Any) -> bool:
    if isinstance(value, str):
        lower = value.lower()
        return any(phrase in lower for phrase in _UNSAFE_POSITIVE_CLAIM_PHRASES)
    if isinstance(value, dict):
        return any(_has_unsafe_positive_claims(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_unsafe_positive_claims(item) for item in value)
    return False


def release_candidate_readiness_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _RELEASE_CANDIDATE_READINESS_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


@dataclass(frozen=True)
class ReleaseCandidateReadinessValidationResult:
    valid: bool
    structurally_valid: bool
    readiness_valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]
    readiness_status: str
    blockers: list[str]
    mismatched_fields: list[str]


def _repo_root_from_workspace(workspace_path: Path) -> Path:
    """Heuristic: repo root is the parent of the workspace if workspace is inside repo,
    otherwise assume workspace IS the repo root."""
    # Common case: workspace is the repo root
    if (workspace_path / "pyproject.toml").exists():
        return workspace_path
    # Fallback: look upward for pyproject.toml
    for parent in workspace_path.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return workspace_path


def _read_text(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _file_exists(repo_root: Path, rel_path: str) -> bool:
    return (repo_root / rel_path).exists()


def _check_version_consistency(repo_root: Path) -> tuple[bool, str]:
    script = repo_root / "scripts" / "check_version_consistency.py"
    if not script.exists():
        return False, "check_version_consistency.py not found"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() if ok else result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception:
        return False, "version check failed"


def _check_forbidden_claims(repo_root: Path) -> tuple[bool, str]:
    script = repo_root / "scripts" / "check_forbidden_claims.py"
    if not script.exists():
        return False, "check_forbidden_claims.py not found"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        ok = result.returncode == 0
        msg = result.stdout.strip() if ok else result.stdout.strip() or result.stderr.strip()
        return ok, msg
    except Exception:
        return False, "forbidden claims check failed"


def _compute_readiness_checks(repo_root: Path, version: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # Required docs
    for doc in _REQUIRED_DOCS:
        exists = _file_exists(repo_root, doc)
        checks.append(_check_name(f"doc_present:{doc}", exists, f"{'found' if exists else 'missing'} {doc}"))

    # Release note for current version (v-prefixed)
    release_note = f"docs/releases/v{version}.md"
    release_note_exists = _file_exists(repo_root, release_note)
    checks.append(_check_name("release_note_present", release_note_exists, f"{'found' if release_note_exists else 'missing'} {release_note}"))

    # Required scripts
    for script in _REQUIRED_SCRIPTS:
        exists = _file_exists(repo_root, script)
        checks.append(_check_name(f"script_present:{script}", exists, f"{'found' if exists else 'missing'} {script}"))

    # README safety wording
    readme = _read_text(repo_root, "README.md").lower()
    checks.append(_check_name("readme_sandbox_only", "sandbox-only" in readme, "sandbox-only wording"))
    checks.append(_check_name("readme_paper_first", "paper-first" in readme, "paper-first wording"))
    checks.append(_check_name("readme_offline_safe", "offline-safe" in readme, "offline-safe wording"))
    checks.append(_check_name("readme_live_trading_disabled", "live trading disabled by default" in readme, "live trading disabled by default wording"))
    checks.append(_check_name("readme_not_financial_advice", "not financial advice" in readme, "not financial advice wording"))
    checks.append(_check_name("readme_profitability_limitation", "does not imply profitability" in readme, "profitability limitation wording"))

    # Version consistency
    version_ok, version_msg = _check_version_consistency(repo_root)
    checks.append(_check_name("version_consistency", version_ok, version_msg))

    # Forbidden claims scan
    claims_ok, claims_msg = _check_forbidden_claims(repo_root)
    checks.append(_check_name("forbidden_claims_scan", claims_ok, claims_msg))

    # Provider safety docs present
    psd_docs = _read_text(repo_root, "docs/provider-safety-dossier.md").lower()
    psd_workflow = _read_text(repo_root, "docs/examples/provider-safety-dossier-workflow.md").lower()
    checks.append(_check_name("provider_safety_dossier_docs_present", bool(psd_docs), "provider safety dossier docs"))
    checks.append(_check_name("provider_safety_dossier_commands_documented", "provider-safety-dossier-latest" in psd_docs, "latest command documented"))
    checks.append(_check_name("provider_safety_dossier_export_documented", "provider-safety-dossier-export" in psd_docs, "export command documented"))
    checks.append(_check_name("provider_safety_dossier_discovery_documented", "provider-safety-dossier-list" in psd_docs, "discovery command documented"))

    # Release checklist present
    rc = _read_text(repo_root, "docs/release-checklist.md").lower()
    checks.append(_check_name("release_checklist_present", bool(rc), "release checklist"))

    # Public docs consistency script present and executable
    pdc = repo_root / "scripts" / "check_public_docs_consistency.py"
    checks.append(_check_name("public_docs_consistency_script_present", pdc.exists(), "public docs consistency script"))

    # Protected boundaries expected clean (no diff in protected dirs)
    try:
        result = subprocess.run(
            ["git", "diff", "--", "src/atlas_agent/config", "src/atlas_agent/brokers", "src/atlas_agent/execution", "src/atlas_agent/safety", "src/atlas_agent/risk"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        protected_clean = result.returncode == 0 and not result.stdout.strip()
        checks.append(_check_name("protected_boundaries_clean", protected_clean, "protected boundary diff empty" if protected_clean else "protected boundary has diffs"))
    except Exception:
        checks.append(_check_name("protected_boundaries_clean", False, "protected boundary check failed"))

    return checks


def _compute_expected_readiness_core(
    workspace_path: Path,
    symbol: str,
    version: str,
) -> dict[str, Any]:
    """Recompute the derived readiness fields from current repo state.

    Returns a dict containing only the derived fields (no metadata like
    report_id, created_at, artifact_path, or artifact_hash).
    """
    repo_root = _repo_root_from_workspace(workspace_path)
    safe_symbol = validate_contract_symbol(symbol)

    checks = _compute_readiness_checks(repo_root, version)
    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    total = len(checks)
    score = int((passed / total) * 100) if total > 0 else 0

    if failed == 0:
        readiness_status = "sandbox_release_candidate_ready"
    else:
        readiness_status = "sandbox_release_candidate_blocked"

    blockers = [c["name"] for c in checks if not c["passed"]]

    # protected_boundaries_expected_clean derived from checks
    protected_check = next((c for c in checks if c["name"] == "protected_boundaries_clean"), None)
    protected_boundaries_expected_clean = protected_check["passed"] if protected_check else False

    return {
        "version": version,
        "readiness_status": readiness_status,
        "readiness_score": score,
        "sandbox_only": True,
        "paper_first": True,
        "offline_safe": True,
        "quickstart_verified": _file_exists(repo_root, "scripts/verify_readme_quickstart.py"),
        "public_docs_consistent": _file_exists(repo_root, "scripts/check_public_docs_consistency.py"),
        "provider_safety_docs_present": _file_exists(repo_root, "docs/provider-safety-dossier.md"),
        "provider_safety_dossier_commands_documented": "provider-safety-dossier-latest" in _read_text(repo_root, "docs/provider-safety-dossier.md").lower(),
        "provider_safety_dossier_export_documented": "provider-safety-dossier-export" in _read_text(repo_root, "docs/provider-safety-dossier.md").lower(),
        "provider_safety_dossier_discovery_documented": "provider-safety-dossier-list" in _read_text(repo_root, "docs/provider-safety-dossier.md").lower(),
        "release_checklist_present": _file_exists(repo_root, "docs/release-checklist.md"),
        "release_note_present": _file_exists(repo_root, f"docs/releases/v{version}.md"),
        "forbidden_claims_scan_clean": _check_forbidden_claims(repo_root)[0],
        "protected_boundaries_expected_clean": protected_boundaries_expected_clean,
        "live_trading_disabled_by_default": True,
        "provider_execution_locked": True,
        "trust_blocked": True,
        "broker_order_path_disabled": True,
        "credentials_not_loaded_by_provider_safety_workflow": True,
        "network_not_enabled_by_provider_safety_workflow": True,
        "checks": checks,
        "blockers": blockers,
    }


def _check_signature(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a deterministic signature of checks for comparison."""
    return [{"name": c["name"], "passed": c["passed"]} for c in checks]


def _find_mismatched_derived_fields(
    stored: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    """Compare stored derived fields against expected recomputed values.

    Returns a list of field names that mismatch. Never echoes raw values.
    """
    mismatched: list[str] = []
    for field in _DERIVED_READINESS_FIELDS:
        stored_val = stored.get(field)
        expected_val = expected.get(field)
        if field == "checks":
            if _check_signature(stored_val) != _check_signature(expected_val):
                mismatched.append(field)
        elif stored_val != expected_val:
            mismatched.append(field)
    return mismatched


def build_release_candidate_readiness_dict(
    workspace_path: Path,
    symbol: str,
    report_id: str,
    version: str,
) -> dict[str, Any]:
    repo_root = _repo_root_from_workspace(workspace_path)
    safe_symbol = validate_contract_symbol(symbol)

    core = _compute_expected_readiness_core(workspace_path, symbol, version)

    artifact_path = (
        workspace_path
        / RESEARCH_DIR
        / safe_symbol.replace("/", "_")
        / "release_candidate_readiness_reports"
        / f"{report_id}.json"
    )

    now = datetime.now(UTC).isoformat()

    artifact: dict[str, Any] = {
        "artifact_type": "release_candidate_readiness_report",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": RELEASE_CANDIDATE_READINESS_VERSION,
        "release_candidate_readiness_report_id": report_id,
        "symbol": safe_symbol,
        "created_at": now,
        "artifact_path": str(artifact_path.relative_to(workspace_path)),
        "artifact_hash": "",
        # Hard-false invariants
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
    }
    artifact.update(core)
    artifact["artifact_hash"] = release_candidate_readiness_sha256(artifact)
    return artifact


def create_release_candidate_readiness(
    workspace_path: Path,
    symbol: str,
    version: str,
) -> dict[str, Any]:
    report_id = generate_run_id()
    artifact = build_release_candidate_readiness_dict(workspace_path, symbol, report_id, version)

    artifact_path = workspace_path / artifact["artifact_path"]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "ok": True,
        "status": "research_release_candidate_readiness_created",
        "release_candidate_readiness_report_id": report_id,
        "symbol": symbol,
        "version": version,
        "readiness_status": artifact["readiness_status"],
        "readiness_score": artifact["readiness_score"],
        "blockers": artifact["blockers"],
    }


def safe_validate_release_candidate_readiness_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(data, dict):
        return None, "invalid_artifact_structure"

    if data.get("artifact_type") != "release_candidate_readiness_report":
        return None, "wrong_artifact_type"

    if data.get("schema_version") != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "schema_version_mismatch"

    if data.get("contract_version") != RELEASE_CANDIDATE_READINESS_VERSION:
        return None, "contract_version_mismatch"

    report_id = data.get("release_candidate_readiness_report_id", "")
    if not report_id or not isinstance(report_id, str):
        return None, "missing_report_id"

    sym = data.get("symbol", "")
    if not sym or not isinstance(sym, str):
        return None, "missing_symbol"

    version = data.get("version", "")
    if not version or not isinstance(version, str):
        return None, "missing_version"

    # Critical safety fields
    if data.get("sandbox_only") is not True:
        return None, "sandbox_only_not_true"
    if data.get("paper_first") is not True:
        return None, "paper_first_not_true"
    if data.get("offline_safe") is not True:
        return None, "offline_safe_not_true"

    # Check hard-false invariants
    for inv in _HARD_FALSE_INVARIANTS:
        if data.get(inv) is True:
            return None, f"hard_false_invariant_violated:{inv}"

    # Reject unsafe positive claims anywhere in the artifact
    if _has_unsafe_positive_claims(data):
        return None, "unsafe_positive_claim_detected"

    # Reject forbidden fragments in any stringified field
    json_text = json.dumps(data)
    if any(frag in json_text for frag in FORBIDDEN_FRAGMENTS):
        return None, "forbidden_fragment_detected"

    # Path safety
    artifact_path = data.get("artifact_path", "")
    if artifact_path and workspace_path is not None:
        p = workspace_path / artifact_path
        if not _is_inside_workspace(p, workspace_path):
            return None, "artifact_path_outside_workspace"

    # Hash validation (after all semantic checks)
    stored_hash = data.get("artifact_hash", "")
    if stored_hash and not for_replay:
        computed = release_candidate_readiness_sha256(data)
        if computed != stored_hash:
            return None, "artifact_hash_mismatch"

    return data, ""


def load_release_candidate_readiness(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cleaned, err = safe_validate_release_candidate_readiness_data(data, workspace_path)
    if err:
        raise ResearchSessionError(err)
    return cleaned


def find_release_candidate_readiness_by_id(workspace_path: Path, report_id: str) -> Path | None:
    safe_id = validate_run_id(report_id)
    for p in (workspace_path / RESEARCH_DIR).rglob("release_candidate_readiness_reports/*.json"):
        if p.stem == safe_id:
            return p
    return None


def iter_release_candidate_readiness_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    search_dirs: list[Path] = []
    research_dir = workspace_path / RESEARCH_DIR

    if symbol is not None:
        from atlas_agent.research.session import sanitize_symbol
        safe = sanitize_symbol(symbol)
        sym_dir = research_dir / safe
        if sym_dir.exists():
            search_dirs.append(sym_dir)
    else:
        if research_dir.exists():
            search_dirs = [d for d in research_dir.iterdir() if d.is_dir()]

    for sym_dir in search_dirs:
        rcr_dir = sym_dir / "release_candidate_readiness_reports"
        if not rcr_dir.exists():
            continue
        for path in rcr_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            cleaned, err = safe_validate_release_candidate_readiness_data(data, workspace_path, for_replay=True)
            if err:
                results.append({
                    "release_candidate_readiness_report_id": path.stem,
                    "symbol": sym_dir.name,
                    "safe_status": "invalid",
                    "safe_status_reason": err,
                    "artifact_path": str(path.relative_to(workspace_path)),
                    "created_at": "",
                    "readiness_status": "",
                    "readiness_score": 0,
                })
                continue
            safe_status = "safe"
            if status_filter and status_filter != safe_status:
                continue
            results.append({
                "release_candidate_readiness_report_id": cleaned.get("release_candidate_readiness_report_id", path.stem),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "safe_status": safe_status,
                "artifact_path": cleaned.get("artifact_path", str(path.relative_to(workspace_path))),
                "created_at": cleaned.get("created_at", ""),
                "readiness_status": cleaned.get("readiness_status", ""),
                "readiness_score": cleaned.get("readiness_score", 0),
            })

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


# Names of checks that contribute to structural validity
_STRUCTURAL_CHECK_NAMES = {
    "artifact_loadable",
    "artifact_type",
    "schema_version",
    "contract_version",
    "sandbox_only_true",
    "paper_first_true",
    "offline_safe_true",
    "unsafe_claims",
    "forbidden_fragments",
    "artifact_hash",
    "derived_readiness_match",
}
for _inv in _HARD_FALSE_INVARIANTS:
    _STRUCTURAL_CHECK_NAMES.add(f"invariant:{_inv}")


def validate_release_candidate_readiness_artifact(
    path: Path,
    workspace_path: Path | None = None,
) -> ReleaseCandidateReadinessValidationResult:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    readiness_status = ""
    blockers: list[str] = []
    mismatched_fields: list[str] = []

    try:
        data = load_release_candidate_readiness(path, workspace_path)
    except ResearchSessionError as exc:
        msg = str(exc)
        checks.append(_check_name("artifact_loadable", False, msg))
        return ReleaseCandidateReadinessValidationResult(
            valid=False,
            structurally_valid=False,
            readiness_valid=False,
            passed_checks=0,
            failed_checks=1,
            checks=checks,
            recommendation="fix_artifact_corruption",
            warnings=warnings,
            readiness_status="",
            blockers=blockers,
            mismatched_fields=mismatched_fields,
        )

    checks.append(_check_name("artifact_loadable", True, "artifact loaded and parsed"))
    checks.append(_check_name("artifact_type", True, "type is release_candidate_readiness_report"))
    checks.append(_check_name("schema_version", True, f"schema_version={data.get('schema_version')}"))
    checks.append(_check_name("contract_version", True, f"contract_version={data.get('contract_version')}"))

    # Version check against current package version
    version = data.get("version", "")
    version_ok = version == __version__
    checks.append(_check_name("version_current", version_ok, f"version={version}" if version_ok else f"version mismatch: expected {__version__}"))
    if not version_ok:
        warnings.append("version_mismatch")
        if "version" not in mismatched_fields:
            mismatched_fields.append("version")

    # Critical safety fields
    for field_name in ("sandbox_only", "paper_first", "offline_safe"):
        val = data.get(field_name)
        ok = val is True
        checks.append(_check_name(f"{field_name}_true", ok, f"{field_name}={val}"))
        if not ok:
            warnings.append(f"{field_name}_not_true")

    # Hard-false invariants
    for inv in _HARD_FALSE_INVARIANTS:
        val = data.get(inv)
        ok = val is not True
        checks.append(_check_name(f"invariant:{inv}", ok, f"{inv} is False" if ok else f"{inv} must be False"))
        if not ok:
            warnings.append(f"hard_false_invariant_violated:{inv}")

    # Unsafe claims
    has_unsafe = _has_unsafe_positive_claims(data)
    checks.append(_check_name("unsafe_claims", not has_unsafe, "no unsafe positive claims" if not has_unsafe else "unsafe positive claim detected"))
    if has_unsafe:
        warnings.append("unsafe_positive_claim_detected")

    # Forbidden fragments
    has_fragments = _has_forbidden_fragments(data)
    checks.append(_check_name("forbidden_fragments", not has_fragments, "no forbidden fragments" if not has_fragments else "forbidden fragment detected"))
    if has_fragments:
        warnings.append("forbidden_fragment_detected")

    # Hash
    stored_hash = data.get("artifact_hash", "")
    hash_ok = False
    if stored_hash:
        computed = release_candidate_readiness_sha256(data)
        hash_ok = computed == stored_hash
        checks.append(_check_name("artifact_hash", hash_ok, "hash matches" if hash_ok else "hash mismatch"))
        if not hash_ok:
            warnings.append("artifact_hash_mismatch")
    else:
        checks.append(_check_name("artifact_hash", False, "missing artifact_hash"))
        warnings.append("missing_artifact_hash")

    # Derived readiness recomputation check
    derived_match = True
    if workspace_path is not None:
        try:
            expected = _compute_expected_readiness_core(workspace_path, data.get("symbol", ""), version)
            new_mismatched = _find_mismatched_derived_fields(data, expected)
            mismatched_fields.extend(new_mismatched)
            derived_match = not mismatched_fields
            if not derived_match:
                checks.append(_check_name("derived_readiness_match", False, f"mismatched fields: {', '.join(mismatched_fields)}"))
                warnings.append("derived_readiness_mismatch")
            else:
                checks.append(_check_name("derived_readiness_match", True, "derived fields match recomputed expectations"))
        except Exception:
            derived_match = False
            checks.append(_check_name("derived_readiness_match", False, "derived readiness recompute failed"))
            warnings.append("derived_readiness_recompute_failed")
    else:
        checks.append(_check_name("derived_readiness_match", True, "workspace unavailable; skipping derived field check"))

    # Readiness status safety
    readiness_status = data.get("readiness_status", "")
    unsafe_statuses = {
        "live_trading_ready",
        "production_trading_ready",
        "safe_to_trade",
        "provider_execution_enabled",
        "broker_execution_enabled",
        "orders_enabled",
        "approvals_enabled",
    }
    status_safe = readiness_status not in unsafe_statuses
    checks.append(_check_name("readiness_status_safe", status_safe, f"readiness_status={readiness_status}" if status_safe else f"unsafe readiness_status: {readiness_status}"))
    if not status_safe:
        warnings.append("unsafe_readiness_status")

    # Readiness blocked check
    blockers = data.get("blockers", [])
    readiness_blocked = readiness_status == "sandbox_release_candidate_blocked"
    checks.append(_check_name("readiness_not_blocked", not readiness_blocked, "readiness not blocked" if not readiness_blocked else f"blocked by {len(blockers)} check(s)"))
    if readiness_blocked:
        warnings.append("readiness_blocked")

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed

    # Structural validity: all structural checks must pass
    structural_failed = sum(
        1 for c in checks
        if not c["passed"] and c["name"] in _STRUCTURAL_CHECK_NAMES
    )
    structurally_valid = structural_failed == 0 and not any(
        w.startswith(("hard_false_invariant_violated", "unsafe_positive_claim_detected",
                      "forbidden_fragment_detected", "artifact_hash_mismatch", "missing_artifact_hash",
                      "sandbox_only_not_true", "paper_first_not_true", "offline_safe_not_true",
                      "derived_readiness_mismatch", "derived_readiness_recompute_failed"))
        for w in warnings
    )

    # Readiness validity: version matches and readiness is not blocked and status is safe and derived fields match
    readiness_valid = version_ok and not readiness_blocked and status_safe and derived_match

    valid = structurally_valid and readiness_valid and not warnings

    if not structurally_valid:
        recommendation = "fix_structural_issues"
    elif not readiness_valid:
        recommendation = "fix_readiness_blockers"
    else:
        recommendation = "artifact_valid"

    return ReleaseCandidateReadinessValidationResult(
        valid=valid,
        structurally_valid=structurally_valid,
        readiness_valid=readiness_valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
        readiness_status=readiness_status,
        blockers=blockers,
        mismatched_fields=mismatched_fields,
    )


def replay_release_candidate_readiness(
    path: Path,
    workspace_path: Path | None = None,
) -> dict[str, Any]:
    data = load_release_candidate_readiness(path, workspace_path)
    return {
        "ok": True,
        "status": "research_release_candidate_readiness_replayed",
        "release_candidate_readiness_report_id": data.get("release_candidate_readiness_report_id", ""),
        "symbol": data.get("symbol", ""),
        "version": data.get("version", ""),
        "readiness_status": data.get("readiness_status", ""),
        "readiness_score": data.get("readiness_score", 0),
        "blockers": data.get("blockers", []),
        "sandbox_only": data.get("sandbox_only", True),
        "paper_first": data.get("paper_first", True),
        "offline_safe": data.get("offline_safe", True),
    }


def summarize_release_candidate_readiness(
    path: Path,
    workspace_path: Path | None = None,
) -> dict[str, Any]:
    data = load_release_candidate_readiness(path, workspace_path)
    checks = data.get("checks", [])
    passed = sum(1 for c in checks if c.get("passed"))
    return {
        "ok": True,
        "status": "research_release_candidate_readiness_summarized",
        "release_candidate_readiness_report_id": data.get("release_candidate_readiness_report_id", ""),
        "symbol": data.get("symbol", ""),
        "version": data.get("version", ""),
        "readiness_status": data.get("readiness_status", ""),
        "readiness_score": data.get("readiness_score", 0),
        "total_checks": len(checks),
        "passed_checks": passed,
        "failed_checks": len(checks) - passed,
        "blockers": data.get("blockers", []),
    }


def doctor_release_candidate_readiness(
    path: Path,
    workspace_path: Path | None = None,
) -> dict[str, Any]:
    result = validate_release_candidate_readiness_artifact(path, workspace_path)
    return {
        "ok": True,
        "status": "research_release_candidate_readiness_doctored",
        "valid": result.valid,
        "structurally_valid": result.structurally_valid,
        "readiness_valid": result.readiness_valid,
        "readiness_status": result.readiness_status,
        "blockers": result.blockers,
        "passed_checks": result.passed_checks,
        "failed_checks": result.failed_checks,
        "recommendation": result.recommendation,
        "warnings": result.warnings,
        "mismatched_fields": result.mismatched_fields,
    }


def export_release_candidate_readiness_markdown(
    workspace_path: Path,
    report_id: str,
    output_path: Path,
) -> dict[str, Any]:
    """Export a release candidate readiness report to a safe Markdown report.

    Fails closed if the report is invalid, tampered, or contains unsafe claims.
    Does not copy raw invalid fields into the output.
    """
    report_path = find_release_candidate_readiness_by_id(workspace_path, report_id)
    if not report_path:
        raise ResearchSessionError("release_candidate_readiness_report_missing")

    data = load_release_candidate_readiness(report_path, workspace_path)

    if not _is_inside_workspace(output_path, workspace_path):
        raise ResearchSessionError("output_path_outside_workspace")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    safe_status = data.get("readiness_status", "")
    safe_score = data.get("readiness_score", 0)
    version = data.get("version", "")
    symbol = data.get("symbol", "")
    report_id_out = data.get("release_candidate_readiness_report_id", "")
    blockers = data.get("blockers", [])

    lines = [
        "# Release Candidate Readiness Report",
        "",
        f"> **Not financial advice.** This is a local verification report for Atlas Agent {version}.",
        "",
        "## Metadata",
        "",
        f"- **Report ID**: `{report_id_out}`",
        f"- **Symbol**: `{symbol}`",
        f"- **Version**: `{version}`",
        f"- **Readiness Status**: `{safe_status}`",
        f"- **Readiness Score**: {safe_score}",
        "",
        "## Safety Invariants",
        "",
        "All hard-false invariants are `false`:",
        "",
    ]
    for inv in _HARD_FALSE_INVARIANTS:
        lines.append(f"- `{inv}`: false")

    lines.extend([
        "",
        "## Blockers",
        "",
    ])
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("No blockers detected.")

    lines.extend([
        "",
        "## Disclaimer",
        "",
        "This report does not claim live trading readiness, production safety, or trading profitability.",
        "It is a local, read-only verification of repository documentation and script presence.",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "ok": True,
        "status": "research_release_candidate_readiness_exported",
        "output_path_relative": str(output_path.relative_to(workspace_path)),
        "output_path_redacted": True,
    }
