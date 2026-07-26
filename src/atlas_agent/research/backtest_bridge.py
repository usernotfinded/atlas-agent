# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/backtest_bridge.py
# PURPOSE: Turns a local research artifact into a paper-only backtest proposal.
#          A research artifact is untrusted text, so it may name a registered
#          strategy and its parameters and nothing else — never a mode, a risk
#          limit, an approval, or an order.
# DEPS:    backtest.registry, backtest.strategy, research.session
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_agent.backtest.registry import default_strategy_registry
from atlas_agent.backtest.strategy import (
    StrategyParameterValidationError,
    coerce_strategy_parameters,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    ResearchSessionError,
    find_research_artifact_by_run_id,
    load_research_artifact,
    sanitize_symbol,
    validate_run_id,
)

# --- CONFIGURATION AND CONSTANTS ---

#: Artifact metadata key holding a structured backtest hypothesis. Prose is never
#: parsed for one: a thesis paragraph does not become a strategy selection just
#: because it mentions a moving average.
HYPOTHESIS_METADATA_KEY = "backtest_hypothesis"

PROPOSAL_ARTIFACT_TYPE = "research_backtest_proposal"
PROPOSAL_SCHEMA_VERSION = RESEARCH_ARTIFACT_SCHEMA_VERSION

#: Every field the bridge is willing to take from an artifact. Anything else in
#: the hypothesis block is reported as unsupported rather than silently ignored,
#: so an artifact cannot smuggle in a setting the operator never reviewed.
SUPPORTED_HYPOTHESIS_KEYS = frozenset({"strategies", "parameters", "rationale"})

STATUS_PROPOSED = "proposed"
STATUS_NO_HYPOTHESIS = "no_hypothesis"
STATUS_HYPOTHESIS_MALFORMED = "hypothesis_malformed"


# ==============================================================================
# BRIDGE WORKFLOW
# ==============================================================================

# --- HYPOTHESIS EXTRACTION ---

def _extract_hypothesis(artifact: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Return the structured hypothesis block and any notes about its shape."""
    metadata = artifact.get("metadata")
    if not isinstance(metadata, dict):
        return None, ["Artifact has no metadata block."]

    if HYPOTHESIS_METADATA_KEY not in metadata:
        return None, [
            f"Artifact metadata has no {HYPOTHESIS_METADATA_KEY!r} block. "
            "The bridge derives nothing from prose, so no strategy is proposed."
        ]

    hypothesis = metadata[HYPOTHESIS_METADATA_KEY]
    if not isinstance(hypothesis, dict):
        return None, [
            f"Artifact metadata {HYPOTHESIS_METADATA_KEY!r} is not an object; ignoring it."
        ]

    notes: list[str] = []
    unsupported = sorted(set(hypothesis) - SUPPORTED_HYPOTHESIS_KEYS)
    if unsupported:
        notes.append(
            "Ignoring unsupported hypothesis field(s): " + ", ".join(unsupported)
        )
    return hypothesis, notes


def _requested_strategy_ids(hypothesis: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """Return the raw strategy entries requested by the artifact."""
    raw = hypothesis.get("strategies")
    if raw is None:
        return [], ["Hypothesis names no strategies."]
    if not isinstance(raw, list):
        return [], ["Hypothesis 'strategies' is not a list; ignoring it."]
    return raw, []


# --- VALIDATION ---

def _rejection(strategy_id: Any, code: str, reason: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id if isinstance(strategy_id, str) else repr(strategy_id),
        "reason_code": code,
        "reason": reason,
    }


def _resolve_parameters(hypothesis: dict[str, Any], strategy_id: str) -> Any:
    """Return the parameter block the artifact supplied for one strategy."""
    parameters = hypothesis.get("parameters")
    if not isinstance(parameters, dict):
        return None
    return parameters.get(strategy_id)


def _evaluate_requested_strategies(
    hypothesis: dict[str, Any],
    requested: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split requested strategies into accepted and rejected entries.

    Every acceptance goes through the registry and the strategy's own parameter
    specs, so an artifact cannot introduce an unregistered strategy or a value
    the strategy would refuse from the CLI.
    """
    # One registry build covers both the membership test and the metadata.
    # Going through the module-level helpers instead would rebuild the registry
    # — and rescan entry points — once per requested strategy.
    registry = default_strategy_registry()
    known = {item.strategy_id: item for item in registry.list_metadata()}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in requested:
        if not isinstance(entry, str) or not entry.strip():
            rejected.append(
                _rejection(entry, "malformed_entry", "Strategy entry is not a non-empty string.")
            )
            continue

        strategy_id = entry.strip()
        if strategy_id in seen:
            rejected.append(
                _rejection(strategy_id, "duplicate_strategy", "Strategy is listed more than once.")
            )
            continue
        seen.add(strategy_id)

        metadata = known.get(strategy_id)
        if metadata is None:
            rejected.append(
                _rejection(
                    strategy_id,
                    "unknown_strategy",
                    "Strategy is not registered; the bridge never invents one.",
                )
            )
            continue

        supplied = _resolve_parameters(hypothesis, strategy_id)
        if supplied is not None and not isinstance(supplied, dict):
            rejected.append(
                _rejection(
                    strategy_id,
                    "invalid_parameters",
                    "Parameter block is not an object.",
                )
            )
            continue

        try:
            parameters = coerce_strategy_parameters(metadata, supplied)
        except StrategyParameterValidationError as exc:
            rejected.append(_rejection(strategy_id, "invalid_parameters", str(exc)))
            continue

        accepted.append(
            {
                "strategy_id": strategy_id,
                "display_name": metadata.name,
                "parameters": parameters,
                "parameters_supplied": supplied is not None,
            }
        )

    return accepted, rejected


# --- ENTRYPOINT ---

def build_backtest_proposal(workspace_path: Path, run_id: str) -> dict[str, Any]:
    """Derive a paper-only backtest proposal from one local research artifact.

    Reads the artifact and nothing else: no provider call, no broker call, no
    order, and no approval. The result describes what an operator could run, it
    does not run or authorize anything.
    """
    safe_run_id = validate_run_id(run_id)

    source_path = find_research_artifact_by_run_id(workspace_path, safe_run_id)
    if source_path is None:
        raise ResearchSessionError("artifact_not_found")
    artifact = load_research_artifact(source_path, workspace_path)

    raw_symbol = artifact.get("symbol")
    if not isinstance(raw_symbol, str):
        raise ResearchSessionError("artifact_malformed")
    # InvalidResearchSymbolError is itself a ResearchSessionError; re-wrapping it
    # would only hide the specific type callers already handle.
    symbol = sanitize_symbol(raw_symbol)

    hypothesis, notes = _extract_hypothesis(artifact)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if hypothesis is None:
        status = STATUS_NO_HYPOTHESIS
    else:
        requested, request_notes = _requested_strategy_ids(hypothesis)
        notes.extend(request_notes)
        accepted, rejected = _evaluate_requested_strategies(hypothesis, requested)
        if accepted:
            status = STATUS_PROPOSED
        elif rejected or request_notes:
            # Something was stated, and none of it survived validation.
            status = STATUS_HYPOTHESIS_MALFORMED
        else:
            status = STATUS_NO_HYPOTHESIS

    raw_rationale = hypothesis.get("rationale") if hypothesis else None
    rationale = raw_rationale if isinstance(raw_rationale, str) else ""

    return {
        "artifact_type": PROPOSAL_ARTIFACT_TYPE,
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "mode": "paper",
        "status": status,
        "symbol": symbol,
        "source_run_id": safe_run_id,
        "source_artifact_path": artifact.get("artifact_path", ""),
        "hypothesis_present": hypothesis is not None,
        "rationale": rationale,
        "accepted_strategies": accepted,
        "rejected_strategies": rejected,
        "notes": notes,
        "safety": {
            "reads_local_artifacts_only": True,
            "creates_pending_orders": False,
            "creates_approvals": False,
            "submits_broker_orders": False,
            "provider_required": False,
            "broker_required": False,
            "network_required": False,
            "live_readiness": False,
            "not_financial_advice": True,
        },
    }
