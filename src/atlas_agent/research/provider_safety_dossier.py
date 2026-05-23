"""Provider safety dossier — offline safety report.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider safety dossier artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.events.log import generate_run_id
from atlas_agent.research.sandbox_contracts import (
    FORBIDDEN_FRAGMENTS,
    _has_forbidden_fragments,
    canonical_json_dumps,
    validate_contract_lineage_id,
    validate_contract_symbol,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    _is_inside_workspace,
    validate_run_id,
)
from atlas_agent.research.provider_mock_response_simulation import (
    find_provider_mock_response_simulation_by_id,
    load_provider_mock_response_simulation,
)
from atlas_agent.research.provider_mock_response_import_candidate import (
    find_provider_mock_response_import_candidate_by_id,
    load_provider_mock_response_import_candidate,
)
from atlas_agent.research.provider_mock_response_review_sandbox import (
    find_provider_mock_response_review_sandbox_by_id,
    load_provider_mock_response_review_sandbox,
)
from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
    find_provider_mock_response_trust_decision_blocker_by_id,
    load_provider_mock_response_trust_decision_blocker,
)
from atlas_agent.research.provider_mock_response_final_safety_seal import (
    find_provider_mock_response_final_safety_seal_by_id,
    load_provider_mock_response_final_safety_seal,
)

PROVIDER_SAFETY_DOSSIER_VERSION = "research_provider_safety_dossier_v1"

_PROVIDER_SAFETY_DOSSIER_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "trust decision granted",
    "trust decision present",
    "trust upgrade performed",
    "trust upgrade available",
    "provider response trusted",
    "mock response trusted",
    "sandbox review trusted",
    "manual review completed",
    "review decision allows trading",
    "review decision allows order creation",
    "create order",
    "approve order",
    "call broker",
    "buy",
    "sell",
    "trading signal",
    "approval created",
    "pending order created",
    "broker touched",
    "real provider response trusted",
    "real provider response reviewed",
    "manual unlock granted",
    "provider call allowed",
    "network enabled",
    "credentials loaded",
    "api key loaded",
    "api call succeeded",
    "live trading authorized",
    "real provider adapter used",
    "real provider request sent",
    "seal authorizes",
    "seal approves",
    "seal permits execution",
    "final seal grants trust",
    "seal unlocks trading",
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

def validate_provider_id(value: str) -> str:
    if not value or value != "mock":
        raise ResearchSessionError("invalid_provider_safety_dossier_provider")
    return value

def provider_safety_dossier_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_SAFETY_DOSSIER_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}

@dataclass(frozen=True)
class ProviderSafetyDossierValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]

def build_provider_safety_dossier_dict(
    workspace_path: Path,
    seal_id: str,
    dossier_id: str,
) -> dict[str, Any]:
    seal_path = find_provider_mock_response_final_safety_seal_by_id(workspace_path, seal_id)
    if not seal_path:
        raise ResearchSessionError("provider_safety_dossier_source_seal_missing")
    seal = load_provider_mock_response_final_safety_seal(seal_path, workspace_path)

    blocker_id = seal.get("source_trust_decision_blocker_id", "")
    blocker_path = find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, blocker_id) if blocker_id else None
    blocker = load_provider_mock_response_trust_decision_blocker(blocker_path, workspace_path) if blocker_path else None

    sandbox_id = blocker.get("source_provider_mock_response_review_sandbox_id", "") if blocker else ""
    sandbox_path = find_provider_mock_response_review_sandbox_by_id(workspace_path, sandbox_id) if sandbox_id else None
    sandbox = load_provider_mock_response_review_sandbox(sandbox_path, workspace_path) if sandbox_path else None

    candidate_id = sandbox.get("source_provider_mock_response_import_candidate_id", "") if sandbox else ""
    candidate_path = find_provider_mock_response_import_candidate_by_id(workspace_path, candidate_id) if candidate_id else None
    candidate = load_provider_mock_response_import_candidate(candidate_path, workspace_path) if candidate_path else None

    simulation_id = candidate.get("source_provider_mock_response_simulation_id", "") if candidate else ""
    simulation_path = find_provider_mock_response_simulation_by_id(workspace_path, simulation_id) if simulation_id else None
    simulation = load_provider_mock_response_simulation(simulation_path, workspace_path) if simulation_path else None


    chain_complete = all([seal, blocker, sandbox, candidate, simulation])

    nodes = []
    if simulation:
        nodes.append({
            "artifact_type": "provider_mock_response_simulation",
            "artifact_id": simulation.get("provider_mock_response_simulation_id", ""),
            "artifact_hash": simulation.get("artifact_hash", ""),
            "source_artifact_id": "",
            "valid": True,
            "provider_id": simulation.get("provider_id", "mock"),
            "created_at": simulation.get("created_at", ""),
            "safe_status": simulation.get("simulation_status", "unknown"),
        })
    if candidate:
        nodes.append({
            "artifact_type": "provider_mock_response_import_candidate",
            "artifact_id": candidate.get("provider_mock_response_import_candidate_id", ""),
            "artifact_hash": candidate.get("artifact_hash", ""),
            "source_artifact_id": simulation_id,
            "valid": True,
            "provider_id": candidate.get("provider_id", "mock"),
            "created_at": candidate.get("created_at", ""),
            "safe_status": candidate.get("import_candidate_status", "unknown"),
        })
    if sandbox:
        nodes.append({
            "artifact_type": "provider_mock_response_review_sandbox",
            "artifact_id": sandbox.get("provider_mock_response_review_sandbox_id", ""),
            "artifact_hash": sandbox.get("artifact_hash", ""),
            "source_artifact_id": candidate_id,
            "valid": True,
            "provider_id": sandbox.get("provider_id", "mock"),
            "created_at": sandbox.get("created_at", ""),
            "safe_status": sandbox.get("review_sandbox_status", "unknown"),
        })
    if blocker:
        nodes.append({
            "artifact_type": "provider_mock_response_trust_decision_blocker",
            "artifact_id": blocker.get("provider_mock_response_trust_decision_blocker_id", ""),
            "artifact_hash": blocker.get("artifact_hash", ""),
            "source_artifact_id": sandbox_id,
            "valid": True,
            "provider_id": blocker.get("provider_id", "mock"),
            "created_at": blocker.get("created_at", ""),
            "safe_status": blocker.get("trust_decision_blocker_status", "unknown"),
        })
    if seal:
        nodes.append({
            "artifact_type": "provider_mock_response_final_safety_seal",
            "artifact_id": seal.get("provider_mock_response_final_safety_seal_id", ""),
            "artifact_hash": seal.get("artifact_hash", ""),
            "source_artifact_id": blocker_id,
            "valid": True,
            "provider_id": seal.get("provider_id", "mock"),
            "created_at": seal.get("created_at", ""),
            "safe_status": seal.get("final_safety_seal_status", "unknown"),
        })

    nodes.append({
        "artifact_type": "provider_safety_dossier",
        "artifact_id": dossier_id,
        "artifact_hash": "",
        "source_artifact_id": seal_id,
        "valid": True,
        "provider_id": "mock",
        "created_at": "",
        "safe_status": "sandbox_chain_complete" if chain_complete else "chain_incomplete",
    })

    chain_health = "complete" if chain_complete else "incomplete"
    safety_verdict = "sandbox_chain_complete" if chain_complete else "chain_incomplete"

    safe_symbol = validate_contract_symbol(seal.get("symbol", "UNKNOWN"))

    artifact_path = (
        workspace_path
        / RESEARCH_DIR
        / safe_symbol.replace("/", "_")
        / "provider_safety_dossiers"
        / f"{dossier_id}.json"
    )

    now = datetime.now(UTC).isoformat()
    nodes[-1]["created_at"] = now

    artifact = {
        "artifact_type": "provider_safety_dossier",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": PROVIDER_SAFETY_DOSSIER_VERSION,
        "provider_safety_dossier_id": dossier_id,
        "source_seal_id": seal_id,
        "source_seal_hash": seal.get("artifact_hash", ""),
        "source_run_id": seal.get("source_run_id", ""),
        "symbol": safe_symbol,
        "provider_id": "mock",
        "sandbox_only": True,
        "chain_complete": chain_complete,
        "chain_health": chain_health,
        "safety_verdict": safety_verdict,
        "chain_nodes": nodes,

        # Hard false invariants
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
        "created_at": now,
        "artifact_path": str(artifact_path.relative_to(workspace_path)),
    }
    artifact["artifact_hash"] = provider_safety_dossier_sha256(artifact)
    return artifact

def create_provider_safety_dossier(workspace_path: Path, seal_id: str) -> dict[str, Any]:
    safe_seal_id = validate_run_id(seal_id)
    dossier_id = generate_run_id()
    artifact = build_provider_safety_dossier_dict(workspace_path, safe_seal_id, dossier_id)

    artifact_path = workspace_path / artifact["artifact_path"]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "ok": True,
        "status": "research_provider_safety_dossier_created",
        "provider_safety_dossier_id": dossier_id,
        "source_seal_id": safe_seal_id,
        "chain_health": artifact["chain_health"],
        "safety_verdict": artifact["safety_verdict"],
    }

def load_provider_safety_dossier(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cleaned, err = safe_validate_provider_safety_dossier_data(data, workspace_path)
    if err:
        raise ResearchSessionError(err)
    return cleaned

def safe_validate_provider_safety_dossier_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(data, dict):
        return None, "provider_safety_dossier_malformed"

    if data.get("artifact_type") != "provider_safety_dossier":
        return None, "provider_safety_dossier_malformed"
    if data.get("schema_version") != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_safety_dossier_schema"
    if data.get("contract_version") != PROVIDER_SAFETY_DOSSIER_VERSION:
        return None, "unsupported_provider_safety_dossier_schema"

    try:
        validate_provider_id(data.get("provider_id", ""))
    except ResearchSessionError:
        return None, "invalid_provider_safety_dossier_provider"

    if data.get("sandbox_only") is not True:
        return None, "provider_safety_dossier_invalid_sandbox_only"

    for flag in [
        "provider_call_allowed", "actual_provider_call_made", "provider_response_trusted",
        "mock_response_trusted", "trading_signal_generated", "approval_created",
        "pending_order_created", "broker_touched", "network_enabled", "credentials_loaded",
        "trust_upgrade_performed", "trust_decision_granted", "provider_execution_unlocked",
        "real_provider_response_imported", "live_trading_path_enabled", "broker_order_path_enabled"
    ]:
        if data.get(flag) is not False:
            return None, "provider_safety_dossier_impossible_boolean"

    if _has_unsafe_positive_claims(data):
        return None, "provider_safety_dossier_forbidden_trust_claim"

    chain_complete = data.get("chain_complete")
    if chain_complete:
        if len(data.get("chain_nodes", [])) < 6:
            return None, "provider_safety_dossier_chain_incomplete"

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_safety_dossier_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_safety_dossier_hash_mismatch"

    if workspace_path and not for_replay:
        seal_id = data.get("source_seal_id", "")
        if seal_id:
            seal_path = find_provider_mock_response_final_safety_seal_by_id(workspace_path, seal_id)
            if not seal_path:
                return None, "provider_safety_dossier_source_seal_missing"
            seal_data = load_provider_mock_response_final_safety_seal(seal_path, workspace_path)
            if seal_data.get("artifact_hash") != data.get("source_seal_hash"):
                return None, "provider_safety_dossier_source_seal_hash_mismatch"

    return dict(data), None

def validate_provider_safety_dossier_artifact(
    path: Path, workspace_path: Path, strict: bool = False
) -> ProviderSafetyDossierValidationResult:
    data = load_provider_safety_dossier(path, workspace_path)
    checks = []

    checks.append(_check_name("schema_version_supported", data.get("schema_version") == RESEARCH_ARTIFACT_SCHEMA_VERSION, ""))
    checks.append(_check_name("artifact_type_correct", data.get("artifact_type") == "provider_safety_dossier", ""))
    checks.append(_check_name("contract_version_supported", data.get("contract_version") == PROVIDER_SAFETY_DOSSIER_VERSION, ""))

    stored_hash = data.get("artifact_hash", "")
    computed_hash = provider_safety_dossier_sha256(data)
    checks.append(_check_name("artifact_hash_match", stored_hash == computed_hash, ""))

    checks.append(_check_name("provider_id_mock", data.get("provider_id") == "mock", ""))
    checks.append(_check_name("sandbox_only_true", data.get("sandbox_only") is True, ""))

    checks.append(_check_name("no_forbidden_positive_claims", not _has_unsafe_positive_claims(data), ""))

    failed = sum(1 for c in checks if not c["passed"])
    return ProviderSafetyDossierValidationResult(
        valid=failed == 0,
        passed_checks=len(checks) - failed,
        failed_checks=failed,
        checks=checks,
        recommendation="ok" if failed == 0 else "reject",
        warnings=[],
    )

def replay_provider_safety_dossier(workspace_path: Path, dossier_id: str) -> dict[str, Any]:
    dossier_path = find_provider_safety_dossier_by_id(workspace_path, dossier_id)
    if not dossier_path:
        raise ResearchSessionError("provider_safety_dossier_missing")
    data = load_provider_safety_dossier(dossier_path, workspace_path)
    return {
        "ok": True,
        "status": "research_provider_safety_dossier_replayed",
        "provider_safety_dossier_id": data.get("provider_safety_dossier_id", ""),
        "replay_hash_match": True,
    }

def summarize_provider_safety_dossier(workspace_path: Path, dossier_id: str) -> dict[str, Any]:
    dossier_path = find_provider_safety_dossier_by_id(workspace_path, dossier_id)
    if not dossier_path:
        raise ResearchSessionError("provider_safety_dossier_missing")
    data = load_provider_safety_dossier(dossier_path, workspace_path)
    return {
        "ok": True,
        "status": "research_provider_safety_dossier_summary",
        "provider_safety_dossier_id": data.get("provider_safety_dossier_id", ""),
        "safety_verdict": data.get("safety_verdict", ""),
        "chain_health": data.get("chain_health", ""),
        "chain_complete": data.get("chain_complete", False),
    }

def doctor_provider_safety_dossier(workspace_path: Path, run_id: str) -> dict[str, Any]:
    dossier_path = _find_latest_provider_safety_dossier_for_run(workspace_path, run_id)
    if not dossier_path:
        return {
            "ok": True,
            "status": "research_provider_safety_dossier_doctor",
            "dossier_health": "missing",
        }
    data = load_provider_safety_dossier(dossier_path, workspace_path)
    return {
        "ok": True,
        "status": "research_provider_safety_dossier_doctor",
        "provider_safety_dossier_id": data.get("provider_safety_dossier_id", ""),
        "dossier_health": "valid",
    }

def export_provider_safety_dossier_markdown(
    workspace_path: Path,
    dossier_id: str,
    output_path: Path,
) -> dict[str, Any]:
    """Export a provider safety dossier to a safe Markdown report.

    Fails closed if the dossier is invalid, tampered, or contains unsafe claims.
    Does not copy raw invalid fields into the output.
    """
    dossier_path = find_provider_safety_dossier_by_id(workspace_path, dossier_id)
    if not dossier_path:
        raise ResearchSessionError("provider_safety_dossier_missing")

    # Load validates schema, booleans, hash, and forbidden claims
    data = load_provider_safety_dossier(dossier_path, workspace_path)

    # Run full artifact validation
    validation = validate_provider_safety_dossier_artifact(dossier_path, workspace_path, strict=False)
    if not validation.valid:
        raise ResearchSessionError("provider_safety_dossier_export_validation_failed")

    # Reject incomplete chains
    if not data.get("chain_complete"):
        raise ResearchSessionError("provider_safety_dossier_export_chain_incomplete")

    # Re-check unsafe claims explicitly (defense in depth)
    if _has_unsafe_positive_claims(data):
        raise ResearchSessionError("provider_safety_dossier_export_unsafe_claim")

    # Safe extraction — only whitelisted fields
    symbol = data.get("symbol", "UNKNOWN")
    provider_id = data.get("provider_id", "mock")
    chain_health = data.get("chain_health", "unknown")
    safety_verdict = data.get("safety_verdict", "unknown")
    chain_nodes = data.get("chain_nodes", [])

    # Build Markdown
    lines = []
    lines.append("# Provider Safety Dossier")
    lines.append("")
    lines.append(f"- **Dossier ID**: `{data.get('provider_safety_dossier_id', '')}`")
    lines.append(f"- **Symbol**: {symbol}")
    lines.append(f"- **Provider ID**: {provider_id}")
    lines.append(f"- **Generated**: {data.get('created_at', '')}")
    lines.append("")

    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"This dossier documents an **offline mock workflow** for the symbol **{symbol}**.")
    lines.append("The workflow is **sandbox-only** and does not involve real provider execution.")
    lines.append("")
    lines.append(f"- **Chain Health**: {chain_health}")
    lines.append(f"- **Safety Verdict**: {safety_verdict}")
    lines.append("")

    lines.append("## 2. Chain")
    lines.append("")
    if chain_nodes:
        lines.append("| Step | Artifact Type | Artifact ID | Safe Status |")
        lines.append("|------|---------------|-------------|-------------|")
        for node in chain_nodes:
            atype = node.get("artifact_type", "unknown")
            aid = node.get("artifact_id", "")
            status = node.get("safe_status", "unknown")
            lines.append(f"| - | {atype} | `{aid}` | {status} |")
    else:
        lines.append("No chain nodes recorded.")
    lines.append("")

    lines.append("## 3. Safety Invariants")
    lines.append("")
    lines.append("The following invariants are enforced and verified:")
    lines.append("")
    lines.append("| Invariant | Value |")
    lines.append("|-----------|-------|")
    for flag in [
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
    ]:
        value = data.get(flag, "missing")
        lines.append(f"| {flag} | {value} |")
    lines.append("")

    lines.append("## 4. Trust Status")
    lines.append("")
    lines.append("- **Trust Decision Granted**: False")
    lines.append("- **Trust Upgrade Performed**: False")
    lines.append("- **Provider Response Trusted**: False")
    lines.append("- **Mock Response Trusted**: False")
    lines.append("- **Sandbox Review Trusted**: False")
    lines.append("")
    lines.append("No trust decisions have been granted. The workflow remains in the offline mock sandbox.")
    lines.append("")

    lines.append("## 5. Execution Status")
    lines.append("")
    lines.append("- **Provider Call Allowed**: False")
    lines.append("- **Actual Provider Call Made**: False")
    lines.append("- **Provider Execution Unlocked**: False")
    lines.append("- **Network Enabled**: False")
    lines.append("- **Credentials Loaded**: False")
    lines.append("")
    lines.append("No provider execution has been authorized or performed.")
    lines.append("")

    lines.append("## 6. Broker/Order Status")
    lines.append("")
    lines.append("- **Trading Signal Generated**: False")
    lines.append("- **Approval Created**: False")
    lines.append("- **Pending Order Created**: False")
    lines.append("- **Broker Touched**: False")
    lines.append("")
    lines.append("No broker or order paths are enabled.")
    lines.append("")

    lines.append("## 7. Validation Result")
    lines.append("")
    lines.append(f"- **Valid**: {validation.valid}")
    lines.append(f"- **Passed Checks**: {validation.passed_checks}")
    lines.append(f"- **Failed Checks**: {validation.failed_checks}")
    lines.append(f"- **Recommendation**: {validation.recommendation}")
    lines.append("")

    lines.append("## 8. Limitations")
    lines.append("")
    lines.append("- This report is generated from an **offline mock workflow**.")
    lines.append("- **No provider execution** has occurred.")
    lines.append("- **No trust upgrade** is available.")
    lines.append("- **No broker/order path** is enabled.")
    lines.append("- **No credentials** were loaded.")
    lines.append("- **No network** was enabled.")
    lines.append("- **Live trading is disabled**.")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by Atlas Agent Provider Safety Dossier Export*")
    lines.append("")

    markdown = "\n".join(lines)

    # Leak-safety scan
    for fragment in FORBIDDEN_FRAGMENTS:
        if fragment in markdown:
            raise ResearchSessionError("provider_safety_dossier_export_forbidden_fragment")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    # Leak-safe path: never return absolute paths; workspace-relative only
    try:
        output_path_relative = str(output_path.relative_to(workspace_path))
    except ValueError:
        output_path_relative = str(output_path.name)

    return {
        "ok": True,
        "status": "research_provider_safety_dossier_exported",
        "provider_safety_dossier_id": data.get("provider_safety_dossier_id", ""),
        "output_path_relative": output_path_relative,
        "output_path_redacted": True,
        "format": "markdown",
    }


def find_provider_safety_dossier_by_id(workspace_path: Path, dossier_id: str) -> Path | None:
    safe_id = validate_run_id(dossier_id)
    search_dir = workspace_path / RESEARCH_DIR
    for p in search_dir.rglob("provider_safety_dossiers/*.json"):
        if p.stem == safe_id:
            return p
    return None

def iter_provider_safety_dossier_artifacts(workspace_path: Path, symbol: str | None = None) -> list[dict[str, Any]]:
    search_dir = workspace_path / RESEARCH_DIR
    if symbol:
        result_dir = search_dir / symbol / "provider_safety_dossiers"
        if not result_dir.exists():
            return []
        paths = list(result_dir.glob("*.json"))
    else:
        paths = list(search_dir.rglob("provider_safety_dossiers/*.json"))

    items = []
    invalid_items = []
    for path in paths:
        if path.is_symlink():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            invalid_items.append({"provider_safety_dossier_id": path.stem, "_invalid": True})
            continue
        cleaned, error = safe_validate_provider_safety_dossier_data(raw, workspace_path=workspace_path)
        if error or not cleaned:
            invalid_items.append({
                "provider_safety_dossier_id": raw.get("provider_safety_dossier_id", path.stem),
                "_invalid": True,
                "error_code": error or "malformed"
            })
            continue
        items.append({
            "provider_safety_dossier_id": cleaned.get("provider_safety_dossier_id", ""),
            "safety_verdict": cleaned.get("safety_verdict", ""),
            "created_at": cleaned.get("created_at", ""),
            "chain_health": cleaned.get("chain_health", ""),
        })
    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    return items + invalid_items

def _find_latest_provider_safety_dossier_for_run(workspace_path: Path, run_id: str) -> Path | None:
    items = iter_provider_safety_dossier_artifacts(workspace_path)
    items = [i for i in items if not i.get("_invalid") and load_provider_safety_dossier(find_provider_safety_dossier_by_id(workspace_path, i["provider_safety_dossier_id"]), workspace_path).get("source_run_id") == run_id]
    if items:
        return find_provider_safety_dossier_by_id(workspace_path, items[0]["provider_safety_dossier_id"])
    return None
