# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/autonomous_paper_scorecard.py
# PURPOSE: Renders the verdict on an autonomous paper run as a signed artifact — the
#          document a human reads when deciding whether this agent has earned more
#          rope.
# DEPS:    agent.autonomous_paper_quality
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# --- CONFIGURATIONS & CONSTANTS ---

# Bumped when the artifact shape changes. The release checkers pin against it, so a
# scorecard from an older schema is rejected rather than silently misread.
ARTIFACT_TYPE = "autonomous_paper_scorecard"
SCHEMA_VERSION = 1
PROMOTION_STATES = (
    "not_evaluated",
    "blocked",
    "paper_quality_observed",
    "eligible_for_shadow_live_review",
)

REQUIRED_DECISION_FIELDS = (
    "run_id",
    "iteration",
    "timestamp",
    "symbol",
    "mode",
    "data_source",
    "strategy_id",
    "proposed_action",
    "risk_result",
    "decision_state",
)

REQUIRED_MANIFEST_FIELDS = (
    "run_id",
    "mode",
    "symbol",
    "strategy_id",
    "data_source",
    "bars_processed",
    "decisions",
    "trades_executed",
    "trades_blocked",
    "no_trade_count",
    "decisions_path",
    "manifest_path",
)

LIVE_SIDE_EFFECT_PATTERNS = (
    "live_trading_enabled",
    "broker.submit",
    "provider.execute",
    "broker.execute",
    "provider.submit",
)

SECRET_LIKE_PATTERNS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "private_key",
    "privatekey",
    "auth_header",
    "bearer ",
    "ghp_",
    "sk-",
)


def _dimension(name: str, passed: bool, score: float, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "score": float(max(0.0, min(1.0, score))),
        "reason": reason,
    }


def _load_decisions(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    decisions: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [], [f"Failed to read decisions file: {exc}"]
    if not text.strip():
        return [], ["Decisions file is empty."]
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Line {line_number}: invalid JSON ({exc})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"Line {line_number}: decision is not a JSON object")
            continue
        decisions.append(obj)
    return decisions, errors


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, [f"Failed to read manifest file: {exc}"]
    if not text.strip():
        return None, ["Manifest file is empty."]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"Manifest is not valid JSON: {exc}"]
    if not isinstance(obj, dict):
        return None, ["Manifest is not a JSON object."]
    return obj, []


def _load_artifacts(
    decisions_path: str | Path,
    manifest_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    d_path = Path(decisions_path)
    m_path = Path(manifest_path)
    errors: list[str] = []

    decisions: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None

    if not d_path.is_file():
        errors.append(f"Decisions file not found: {d_path}")
    else:
        decisions, d_errors = _load_decisions(d_path)
        errors.extend(d_errors)

    if not m_path.is_file():
        errors.append(f"Manifest file not found: {m_path}")
    else:
        manifest, m_errors = _load_manifest(m_path)
        errors.extend(m_errors)

    return decisions, manifest, errors


def _has_secret_like(text: str) -> tuple[bool, str]:
    lowered = text.lower()
    for pattern in SECRET_LIKE_PATTERNS:
        if pattern in lowered:
            return True, f"Artifact text contains secret-like pattern: {pattern!r}"
    return False, ""


def _artifact_text(decisions: list[dict[str, Any]], manifest: dict[str, Any] | None) -> str:
    parts: list[str] = [json.dumps(manifest, sort_keys=True) if manifest else ""]
    parts.extend(json.dumps(d, sort_keys=True) for d in decisions)
    return "\n".join(parts)


def _check_schema_validity(
    decisions: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    load_errors: list[str],
) -> dict[str, Any]:
    failures: list[str] = list(load_errors)
    if manifest is None:
        failures.append("Manifest is missing or unreadable.")
    else:
        missing_manifest = [f for f in REQUIRED_MANIFEST_FIELDS if f not in manifest]
        if missing_manifest:
            failures.append(f"Manifest missing fields: {missing_manifest}")
    for idx, decision in enumerate(decisions):
        missing = [f for f in REQUIRED_DECISION_FIELDS if f not in decision]
        if missing:
            failures.append(f"Decision {idx} missing fields: {missing}")
    if failures:
        return _dimension(
            "schema_validity",
            False,
            0.0,
            "; ".join(failures),
        )
    return _dimension(
        "schema_validity",
        True,
        1.0,
        "All required decision and manifest fields present.",
    )


def _check_replay_determinism(
    decisions: list[dict[str, Any]],
    manifest: dict[str, Any],
    replay_decisions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    failures: list[str] = []

    run_ids = {str(d.get("run_id", "")) for d in decisions}
    if len(run_ids) > 1:
        failures.append(f"Decisions contain multiple run_ids: {sorted(run_ids)}")

    expected_iterations = list(range(len(decisions)))
    actual_iterations = [d.get("iteration") for d in decisions]
    if actual_iterations != expected_iterations:
        failures.append(
            f"Iterations not sequential 0..N-1: expected {expected_iterations}, got {actual_iterations}"
        )

    timestamps: list[str] = [str(d.get("timestamp", "")) for d in decisions]
    if len(timestamps) > 1:
        for i in range(len(timestamps) - 1):
            if timestamps[i] > timestamps[i + 1]:
                failures.append(f"Timestamps not monotonic at iteration {i}")
                break

    manifest_decisions = manifest.get("decisions")
    if manifest_decisions is not None and len(decisions) != int(manifest_decisions):
        failures.append(
            f"Decision count mismatch: manifest says {manifest_decisions}, found {len(decisions)}"
        )

    if replay_decisions is not None:
        if len(decisions) != len(replay_decisions):
            failures.append(
                f"Replay decision count mismatch: original {len(decisions)}, replay {len(replay_decisions)}"
            )
        else:
            for idx, (orig, replay) in enumerate(zip(decisions, replay_decisions)):
                if orig.get("decision_state") != replay.get("decision_state"):
                    failures.append(
                        f"Replay decision_state mismatch at iteration {idx}: "
                        f"{orig.get('decision_state')} != {replay.get('decision_state')}"
                    )
                if orig.get("proposed_action") != replay.get("proposed_action"):
                    failures.append(
                        f"Replay proposed_action mismatch at iteration {idx}: "
                        f"{orig.get('proposed_action')} != {replay.get('proposed_action')}"
                    )

    if failures:
        return _dimension("replay_determinism", False, 0.0, "; ".join(failures))
    return _dimension(
        "replay_determinism",
        True,
        1.0,
        "Run identifiers, iterations, timestamps, and counts are consistent.",
    )


def _check_risk_gate_compliance(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for idx, decision in enumerate(decisions):
        state = decision.get("decision_state")
        risk_result = decision.get("risk_result") or {}
        allowed = risk_result.get("allowed")
        if state == "paper_executed" and allowed is not True:
            failures.append(
                f"Iteration {idx}: paper_executed but risk_result.allowed={allowed}"
            )
        if state == "risk_blocked" and allowed is not False:
            failures.append(
                f"Iteration {idx}: risk_blocked but risk_result.allowed={allowed}"
            )
    if failures:
        return _dimension("risk_gate_compliance", False, 0.0, "; ".join(failures))
    return _dimension(
        "risk_gate_compliance",
        True,
        1.0,
        "Risk gate states are consistent with allowed flags.",
    )


def _check_kill_switch_compliance(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    kill_switch_present = False
    for decision in decisions:
        risk_result = decision.get("risk_result") or {}
        violations = risk_result.get("violations") or []
        for violation in violations:
            if isinstance(violation, dict) and violation.get("rule") == "kill_switch":
                kill_switch_present = True
                break
        if kill_switch_present:
            break

    if not kill_switch_present:
        return _dimension(
            "kill_switch_compliance",
            True,
            1.0,
            "No kill-switch violations observed.",
        )

    executed = [idx for idx, d in enumerate(decisions) if d.get("decision_state") == "paper_executed"]
    if executed:
        return _dimension(
            "kill_switch_compliance",
            False,
            0.0,
            f"Kill-switch violation present but trades executed at iterations {executed}.",
        )
    return _dimension(
        "kill_switch_compliance",
        True,
        1.0,
        "Kill-switch violation present and no trades were executed.",
    )


def _check_no_live_side_effects(
    decisions: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    failures: list[str] = []

    modes = {str(d.get("mode", "")).lower() for d in decisions}
    manifest_mode = str(manifest.get("mode", "")).lower()
    if modes - {"paper"}:
        failures.append(f"Decision modes are not all 'paper': {sorted(modes)}")
    if manifest_mode != "paper":
        failures.append(f"Manifest mode is not 'paper': {manifest_mode!r}")

    text = _artifact_text(decisions, manifest).lower()
    for pattern in LIVE_SIDE_EFFECT_PATTERNS:
        if pattern in text:
            failures.append(f"Artifact text contains live side-effect reference: {pattern!r}")

    if failures:
        return _dimension("no_live_side_effects", False, 0.0, "; ".join(failures))
    return _dimension(
        "no_live_side_effects",
        True,
        1.0,
        "All artifacts are paper mode with no live broker/provider references.",
    )


def _check_audit_redaction(
    decisions: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    text = _artifact_text(decisions, manifest)
    has_secret, reason = _has_secret_like(text)
    if has_secret:
        return _dimension("audit_redaction", False, 0.0, reason)
    return _dimension(
        "audit_redaction",
        True,
        1.0,
        "No secret-like patterns detected in artifact text.",
    )


def _check_decision_coverage(
    decisions: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    if not decisions:
        return _dimension(
            "decision_coverage",
            False,
            0.0,
            "No decisions found.",
        )
    manifest_decisions = manifest.get("decisions")
    if manifest_decisions is not None and len(decisions) != int(manifest_decisions):
        return _dimension(
            "decision_coverage",
            False,
            0.0,
            f"Manifest decision count {manifest_decisions} does not match actual {len(decisions)}.",
        )
    return _dimension(
        "decision_coverage",
        True,
        1.0,
        f"{len(decisions)} decisions present and match manifest count.",
    )


def _check_blocked_reason_quality(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for idx, decision in enumerate(decisions):
        if decision.get("decision_state") != "risk_blocked":
            continue
        if not decision.get("blocked_reason"):
            failures.append(f"Iteration {idx}: risk_blocked decision has empty blocked_reason")
        risk_result = decision.get("risk_result") or {}
        violations = risk_result.get("violations")
        if not violations:
            failures.append(f"Iteration {idx}: risk_blocked decision has no risk violations")
    if failures:
        return _dimension("blocked_reason_quality", False, 0.0, "; ".join(failures))
    return _dimension(
        "blocked_reason_quality",
        True,
        1.0,
        "All risk_blocked decisions include reasons and violations.",
    )


def _check_no_trade_reason_quality(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for idx, decision in enumerate(decisions):
        if decision.get("decision_state") != "no_trade":
            continue
        if decision.get("proposed_action") != "hold":
            failures.append(
                f"Iteration {idx}: no_trade decision has proposed_action={decision.get('proposed_action')!r}"
            )
        if decision.get("proposed_order") is not None:
            failures.append(f"Iteration {idx}: no_trade decision has a proposed_order")
        risk_result = decision.get("risk_result") or {}
        if risk_result.get("status") != "not_applicable":
            failures.append(
                f"Iteration {idx}: no_trade decision risk_result.status={risk_result.get('status')!r}"
            )
    if failures:
        return _dimension("no_trade_reason_quality", False, 0.0, "; ".join(failures))
    return _dimension(
        "no_trade_reason_quality",
        True,
        1.0,
        "All no_trade decisions are hold actions with no proposed order.",
    )


def _check_artifact_completeness(
    decisions_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    if not decisions_path.is_file() or decisions_path.stat().st_size == 0:
        failures.append(f"Decisions file missing or empty: {decisions_path}")
    if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
        failures.append(f"Manifest file missing or empty: {manifest_path}")

    referenced_decisions = manifest.get("decisions_path")
    referenced_manifest = manifest.get("manifest_path")
    if referenced_decisions and Path(referenced_decisions).resolve() != decisions_path.resolve():
        failures.append(
            f"Manifest decisions_path {referenced_decisions!r} does not match {decisions_path}"
        )
    if referenced_manifest and Path(referenced_manifest).resolve() != manifest_path.resolve():
        failures.append(
            f"Manifest manifest_path {referenced_manifest!r} does not match {manifest_path}"
        )

    if failures:
        return _dimension("artifact_completeness", False, 0.0, "; ".join(failures))
    return _dimension(
        "artifact_completeness",
        True,
        1.0,
        "Both artifact files exist, are non-empty, and manifest references them.",
    )


def _determine_promotion_state(
    manifest: dict[str, Any] | None,
    dimensions: dict[str, dict[str, Any]],
    blockers: list[str],
) -> tuple[str, list[str]]:
    if not dimensions:
        return "not_evaluated", ["Missing or unreadable artifacts."]

    critical = [
        "schema_validity",
        "no_live_side_effects",
        "audit_redaction",
        "artifact_completeness",
    ]
    for name in critical:
        if not dimensions.get(name, {}).get("passed"):
            return "blocked", blockers + [f"Critical dimension failed: {name}"]

    safety = [
        "risk_gate_compliance",
        "kill_switch_compliance",
        "no_live_side_effects",
        "audit_redaction",
    ]
    safety_pass = all(dimensions.get(n, {}).get("passed") for n in safety)
    prereq_pass = dimensions.get("future_shadow_live_prerequisites", {}).get("passed")
    if safety_pass and prereq_pass:
        return "eligible_for_shadow_live_review", blockers

    if dimensions.get("schema_validity", {}).get("passed") and dimensions.get(
        "artifact_completeness", {}
    ).get("passed"):
        return "paper_quality_observed", blockers

    return "blocked", blockers


def _empty_scorecard(errors: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": "paper",
        "run_id": None,
        "promotion_state": "not_evaluated",
        "blockers": errors or ["Missing or unreadable artifacts."],
        "scorecard_dimensions": {},
        "safety": {
            "risk_gate_compliance": False,
            "kill_switch_compliance": False,
            "no_live_side_effects": False,
            "audit_redaction": False,
        },
        "manifest_summary": {
            "bars_processed": 0,
            "decisions": 0,
            "trades_executed": 0,
            "trades_blocked": 0,
            "no_trade_count": 0,
        },
    }


def build_autonomous_paper_scorecard(
    decisions_path: str | Path,
    manifest_path: str | Path,
    *,
    replay_decisions_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic offline scorecard for autonomous-paper artifacts.

    This function never calls brokers, providers, or loads credentials. It only
    reads local ``decisions.jsonl`` and ``manifest.json`` artifacts.
    """
    d_path = Path(decisions_path)
    m_path = Path(manifest_path)

    decisions, manifest, errors = _load_artifacts(d_path, m_path)
    if errors and not decisions and not manifest:
        return _empty_scorecard(errors)

    replay_decisions: list[dict[str, Any]] | None = None
    if replay_decisions_path is not None:
        replay_decisions, replay_errors = _load_decisions(Path(replay_decisions_path))
        if replay_errors:
            errors.extend(replay_errors)

    # Both files missing means there is nothing to evaluate.
    if not d_path.is_file() and not m_path.is_file():
        return _empty_scorecard(errors)

    effective_manifest = manifest if manifest is not None else {}

    schema_dim = _check_schema_validity(decisions, manifest, errors)
    replay_dim = _check_replay_determinism(decisions, effective_manifest, replay_decisions)
    risk_gate_dim = _check_risk_gate_compliance(decisions)
    kill_switch_dim = _check_kill_switch_compliance(decisions)
    no_live_dim = _check_no_live_side_effects(decisions, effective_manifest)
    redaction_dim = _check_audit_redaction(decisions, effective_manifest)
    coverage_dim = _check_decision_coverage(decisions, effective_manifest)
    blocked_reason_dim = _check_blocked_reason_quality(decisions)
    no_trade_dim = _check_no_trade_reason_quality(decisions)
    completeness_dim = _check_artifact_completeness(d_path, m_path, effective_manifest)

    # Future shadow-live prerequisites require state diversity and all safety dims.
    safety_dims = {
        "risk_gate_compliance": risk_gate_dim,
        "kill_switch_compliance": kill_switch_dim,
        "no_live_side_effects": no_live_dim,
        "audit_redaction": redaction_dim,
    }
    states = [d.get("decision_state") for d in decisions]
    prereq_failures: list[str] = []
    status = effective_manifest.get("status", "completed")
    if status != "completed":
        prereq_failures.append(f"Run status is not 'completed': {status!r}")
    if "paper_executed" not in states:
        prereq_failures.append("No paper_executed decisions observed.")
    if "no_trade" not in states:
        prereq_failures.append("No no_trade decisions observed.")
    if "risk_blocked" not in states:
        prereq_failures.append("No risk_blocked decisions observed.")
    for name, dim in safety_dims.items():
        if not dim["passed"]:
            prereq_failures.append(f"Safety dimension failed: {name}")
    prereq_dim = _dimension(
        "future_shadow_live_prerequisites",
        not prereq_failures,
        1.0 if not prereq_failures else 0.0,
        "; ".join(prereq_failures) if prereq_failures else "Run demonstrates required state diversity and safety.",
    )

    dimensions: dict[str, dict[str, Any]] = {
        "schema_validity": schema_dim,
        "replay_determinism": replay_dim,
        "risk_gate_compliance": risk_gate_dim,
        "kill_switch_compliance": kill_switch_dim,
        "no_live_side_effects": no_live_dim,
        "audit_redaction": redaction_dim,
        "decision_coverage": coverage_dim,
        "blocked_reason_quality": blocked_reason_dim,
        "no_trade_reason_quality": no_trade_dim,
        "artifact_completeness": completeness_dim,
        "future_shadow_live_prerequisites": prereq_dim,
    }

    blockers = [d["reason"] for d in dimensions.values() if not d["passed"]]
    state, final_blockers = _determine_promotion_state(effective_manifest, dimensions, blockers)

    # A provided replay is a verification contract; mismatches are treated as blocking
    # because they indicate the artifact is not reproducible.
    if replay_decisions_path is not None and not dimensions.get("replay_determinism", {}).get("passed"):
        state = "blocked"
        final_blockers = final_blockers + ["Replay determinism verification failed."]

    run_id = effective_manifest.get("run_id")
    if not run_id and decisions:
        run_id = decisions[0].get("run_id")

    summary = {
        "bars_processed": effective_manifest.get("bars_processed", 0),
        "decisions": effective_manifest.get("decisions", len(decisions)),
        "trades_executed": effective_manifest.get("trades_executed", 0),
        "trades_blocked": effective_manifest.get("trades_blocked", 0),
        "no_trade_count": effective_manifest.get("no_trade_count", 0),
    }

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "mode": "paper",
        "run_id": run_id,
        "status": effective_manifest.get("status", "completed"),
        "promotion_state": state,
        "blockers": final_blockers,
        "scorecard_dimensions": dimensions,
        "safety": {name: dim["passed"] for name, dim in safety_dims.items()},
        "manifest_summary": summary,
        **summary,
        "decisions_path": str(d_path),
        "manifest_path": str(m_path),
        "replay_decisions_path": str(replay_decisions_path) if replay_decisions_path else None,
    }


def render_autonomous_paper_scorecard_markdown(scorecard: dict[str, Any]) -> str:
    """Render a Markdown report from an autonomous-paper scorecard."""
    state = scorecard.get("promotion_state", "unknown")
    blockers = scorecard.get("blockers", [])
    dimensions = scorecard.get("scorecard_dimensions", {})
    safety = scorecard.get("safety", {})
    summary = scorecard.get("manifest_summary", {})
    run_id = scorecard.get("run_id") or "unknown"

    lines: list[str] = []
    lines.append("# Autonomous Paper Scorecard")
    lines.append("")
    lines.append("> **Planning-only status.** This scorecard evaluates paper-trading artifacts offline. "
                 "It is a statement of **not live-trading readiness** and does **not** authorize "
                 "autonomous live order submission.")
    lines.append("")
    lines.append("> **Not financial advice.**")
    lines.append("")

    lines.append("## Run summary")
    lines.append("")
    lines.append(f"- **Artifact type:** {scorecard.get('artifact_type', ARTIFACT_TYPE)}")
    lines.append(f"- **Schema version:** {scorecard.get('schema_version', SCHEMA_VERSION)}")
    lines.append(f"- **Mode:** {scorecard.get('mode', 'paper')}")
    lines.append(f"- **Run ID:** {run_id}")
    lines.append(f"- **Promotion state:** `{state}`")
    lines.append("")

    lines.append("## Safety flags")
    lines.append("")
    lines.append("| Dimension | Passed |")
    lines.append("|---|---|")
    for name, passed in safety.items():
        lines.append(f"| {name} | {'✅' if passed else '❌'} |")
    lines.append("")

    lines.append("## Manifest summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for key, value in summary.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")

    lines.append("## Scorecard dimensions")
    lines.append("")
    lines.append("| Dimension | Passed | Score | Reason |")
    lines.append("|---|---|---|---|")
    for name, dim in dimensions.items():
        passed = dim.get("passed", False)
        score = dim.get("score", 0.0)
        reason = dim.get("reason", "")
        lines.append(f"| {name} | {'✅' if passed else '❌'} | {score:.2f} | {reason} |")
    lines.append("")

    lines.append("## Blockers")
    lines.append("")
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("No blockers recorded.")
    lines.append("")

    lines.append("## Promotion gate interpretation")
    lines.append("")
    lines.append(
        f"The current promotion state is **`{state}`**. A state of "
        "`eligible_for_shadow_live_review` only indicates that the paper artifact "
        "meets conservative offline criteria for a future human-reviewed shadow-live "
        "evaluation. It does **not** mean the strategy is safe, profitable, or ready "
        "for unattended live trading. All shadow-live transitions require explicit "
        "human approval, broker sync checks, and additional governance.")
    lines.append("")

    return "\n".join(lines)


def write_autonomous_paper_scorecard_reports(
    scorecard: dict[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write scorecard JSON and Markdown reports to ``output_dir``."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "autonomous-paper-scorecard.json"
    md_path = destination / "autonomous-paper-scorecard.md"
    json_path.write_text(
        json.dumps(scorecard, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_autonomous_paper_scorecard_markdown(scorecard), encoding="utf-8")
    return json_path, md_path
