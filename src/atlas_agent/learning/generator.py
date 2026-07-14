# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/generator.py
# PURPOSE: Produces learning suggestions. With provider execution disabled (the
#          default) it emits a suggestion explicitly LABELLED as such, rather than
#          inventing a plausible-sounding insight.
# DEPS:    learning.models
#
# DESIGN:  "No fake insights" is the load-bearing rule. A fabricated lesson about
#          the user's own trading would be believed — it looks exactly like a real
#          one — so the absence of a model must be stated in the output, never
#          papered over.
# ==============================================================================

"""Learning suggestion generator with dry-run/static fallback.

When provider execution is disabled (the default), the generator produces a
structured static learning suggestion that clearly marks `provider_execution_disabled`.
No fake insights are invented. If input data is missing, the suggestion says so.
"""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_agent.learning.models import (
    LearningSuggestion,
    SuggestionProvenance,
    SuggestionStatus,
)


def _read_input_text(path: Path) -> str:
    """Safely read input file text."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _generate_static_summary(
    text: str,
    kind: str,
    source_name: str,
) -> str:
    """Generate a safe, non-fake summary."""
    if not text:
        return "No input data available."
    return (
        f"Static learning suggestion derived from {kind} artifact ({source_name}). "
        "Provider execution is disabled. Suggestion was generated using a local static fallback. "
        "This is advisory-only and not automatically executable."
    )


def _generate_static_evidence(text: str, kind: str) -> list[str]:
    """Generate safe evidence based on input."""
    evidence: list[str] = []
    if not text:
        evidence.append("No input data was available during generation.")
        return evidence
    lines = text.splitlines()
    evidence.append(f"Input contains {len(lines)} lines.")
    header_count = sum(1 for line in lines if line.strip().startswith("#"))
    if header_count:
        evidence.append(f"Contains {header_count} markdown headers.")
    if kind == "reflection":
        if "observation" in text.lower():
            evidence.append("Reflection contains observations.")
        if "question" in text.lower():
            evidence.append("Reflection contains review questions.")
    elif kind == "skill":
        if "limitation" in text.lower():
            evidence.append("Skill lists limitations.")
        if "safety" in text.lower():
            evidence.append("Skill lists safety notes.")
    elif kind == "report":
        if "portfolio" in text.lower():
            evidence.append("Report references portfolio data.")
        if "backtest" in text.lower():
            evidence.append("Report references backtest data.")
    return evidence


def _generate_static_limitations(text: str) -> list[str]:
    """Generate safe limitations."""
    limitations = [
        "This suggestion is generated statically and does not contain original insights.",
        "Operator review is required before operational use.",
        "Provider execution remains disabled by default.",
        "Broker execution remains disabled by default.",
        "Skills are not automatically activated.",
    ]
    if not text:
        limitations.append("No input data was available during generation.")
    return limitations


def _generate_safety_notes() -> list[str]:
    """Generate safety notes."""
    return [
        "Not financial advice.",
        "Not a trading instruction.",
        "Not automatically executable.",
        "Requires explicit human review before action.",
        "No skill auto-activation.",
    ]


def _generate_title(text: str, kind: str) -> str:
    """Generate a title from input."""
    if not text:
        return f"Untitled {kind} learning suggestion"
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or f"Untitled {kind} learning suggestion"
    return f"Untitled {kind} learning suggestion"


def _detect_kind(path: Path) -> str:
    """Best-effort detection of input artifact kind from path."""
    name = path.name.lower()
    parent = path.parent.name.lower()
    if "backtest" in name or "backtest" in parent:
        return "backtest"
    if "report" in name or "report" in parent:
        return "report"
    if "research" in name or "research" in parent:
        return "research"
    if "audit" in name or "audit" in parent:
        return "audit"
    if "note" in name:
        return "note"
    if "reflection" in name or "reflection" in parent:
        return "reflection"
    if "skill" in name or "skill" in parent:
        return "skill"
    return "general"


def generate_suggestion_from_reflection(
    reflection_id: str,
    reflection_path: str,
    reflection_text: str,
    *,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> LearningSuggestion:
    """Generate a learning suggestion from a reflection artifact.

    Parameters
    ----------
    reflection_id: ID of the source reflection
    reflection_path: path to the source reflection artifact
    reflection_text: text content of the reflection
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    LearningSuggestion with provider_execution_disabled=True when dry_run=True
    """
    kind = "reflection"
    title = _generate_title(reflection_text, kind)
    summary = _generate_static_summary(reflection_text, kind, reflection_path)
    evidence = _generate_static_evidence(reflection_text, kind)
    limitations = _generate_static_limitations(reflection_text)
    safety_notes = _generate_safety_notes()

    provenance = SuggestionProvenance(
        source_reflection_id=reflection_id,
        source_path=reflection_path,
        source_kind=kind,
        workspace=str(workspace),
        provider_execution_disabled=True,
        static_fallback=True,
    )

    return LearningSuggestion(
        title=title,
        summary=summary,
        kind=kind,
        provenance=provenance,
        evidence=evidence,
        limitations=limitations,
        safety_notes=safety_notes,
        recommended_next_step="Review the source reflection and decide if a skill candidate should be created.",
        execution_policy="advisory_only",
        status=SuggestionStatus.draft,
    )


def generate_suggestion_from_skill(
    skill_id: str,
    skill_path: str,
    skill_text: str,
    *,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> LearningSuggestion:
    """Generate a learning suggestion from an approved skill library entry.

    Parameters
    ----------
    skill_id: ID of the source skill
    skill_path: path to the source skill artifact
    skill_text: text content of the skill
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    LearningSuggestion with provider_execution_disabled=True when dry_run=True
    """
    kind = "skill"
    title = _generate_title(skill_text, kind)
    summary = _generate_static_summary(skill_text, kind, skill_path)
    evidence = _generate_static_evidence(skill_text, kind)
    limitations = _generate_static_limitations(skill_text)
    safety_notes = _generate_safety_notes()

    provenance = SuggestionProvenance(
        source_skill_id=skill_id,
        source_path=skill_path,
        source_kind=kind,
        workspace=str(workspace),
        provider_execution_disabled=True,
        static_fallback=True,
    )

    return LearningSuggestion(
        title=title,
        summary=summary,
        kind=kind,
        provenance=provenance,
        evidence=evidence,
        limitations=limitations,
        safety_notes=safety_notes,
        recommended_next_step="Review the source skill and consider whether it can be improved or extended.",
        execution_policy="advisory_only",
        status=SuggestionStatus.draft,
    )


def generate_suggestion_from_input(
    input_path: str | Path,
    *,
    kind: str | None = None,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> LearningSuggestion:
    """Generate a learning suggestion from a local input file.

    Parameters
    ----------
    input_path: path to the input artifact file
    kind: optional kind override (report, backtest, research, audit, note, reflection, skill)
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    LearningSuggestion with provider_execution_disabled=True when dry_run=True
    """
    path = Path(input_path)
    text = _read_input_text(path)
    detected_kind = kind or _detect_kind(path)

    title = _generate_title(text, detected_kind)
    summary = _generate_static_summary(text, detected_kind, path.name)
    evidence = _generate_static_evidence(text, detected_kind)
    limitations = _generate_static_limitations(text)
    safety_notes = _generate_safety_notes()

    provenance = SuggestionProvenance(
        source_path=str(path),
        source_kind=detected_kind,
        workspace=str(workspace),
        provider_execution_disabled=True,
        static_fallback=True,
    )

    return LearningSuggestion(
        title=title,
        summary=summary,
        kind=detected_kind,
        provenance=provenance,
        evidence=evidence,
        limitations=limitations,
        safety_notes=safety_notes,
        recommended_next_step="Review the input artifact and determine if any learning or process improvement is warranted.",
        execution_policy="advisory_only",
        status=SuggestionStatus.draft,
    )
