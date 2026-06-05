"""Skill candidate generator with dry-run/static fallback.

When provider execution is disabled (the default), the generator produces a
structured static skill candidate that clearly marks `provider_execution_disabled`.
No fake insights are invented. If input data is missing, the candidate says so.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas_agent.reflection.models import ReflectionArtifact
from atlas_agent.skills.models import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillProvenance,
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
        f"Static skill candidate derived from {kind} artifact ({source_name}). "
        "Provider execution is disabled. Candidate was generated using a local static fallback."
    )


def _generate_static_limitations(text: str) -> list[str]:
    """Generate safe limitations based on input."""
    limitations = [
        "This candidate is generated statically and does not contain original insights.",
        "Operator review is required before operational use.",
        "Provider execution remains disabled by default.",
        "Broker execution remains disabled by default.",
    ]
    if not text:
        limitations.append("No input data was available during generation.")
    return limitations


def _generate_safety_notes(text: str) -> list[str]:
    """Generate safety notes."""
    return [
        "Not financial advice.",
        "Not a trading instruction.",
        "Not automatically active.",
        "Requires explicit human approval before promotion.",
    ]


def _generate_title(text: str, kind: str) -> str:
    """Generate a title from input."""
    if not text:
        return f"Untitled {kind} skill candidate"
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or f"Untitled {kind} skill candidate"
    return f"Untitled {kind} skill candidate"


def generate_candidate_from_reflection(
    reflection: ReflectionArtifact,
    *,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> SkillCandidate:
    """Generate a skill candidate from a reflection artifact.

    Parameters
    ----------
    reflection: a ReflectionArtifact
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    SkillCandidate with provider_execution_disabled=True when dry_run=True
    """
    source_path = reflection.provenance.input_artifact.path
    source_kind = reflection.provenance.input_artifact.kind or "unknown"
    source_reflection_id = reflection.reflection_id

    text = ""
    if source_path:
        text = _read_input_text(Path(source_path))

    title = _generate_title(text, source_kind)
    summary = _generate_static_summary(text, source_kind, Path(source_path).name if source_path else "unknown")
    limitations = _generate_static_limitations(text)
    safety_notes = _generate_safety_notes(text)

    provenance = SkillProvenance(
        source_reflection_id=source_reflection_id,
        source_path=source_path,
        source_kind=source_kind,
        workspace=str(workspace),
        provider_execution_disabled=True,
        static_fallback=True,
    )

    return SkillCandidate(
        title=title,
        summary=summary,
        kind=source_kind,
        provenance=provenance,
        limitations=limitations,
        safety_notes=safety_notes,
        activation_policy="manual_only",
        status=SkillCandidateStatus.draft,
    )


def generate_candidate_from_input(
    input_path: str | Path,
    *,
    kind: str | None = None,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> SkillCandidate:
    """Generate a skill candidate from a local input file.

    Parameters
    ----------
    input_path: path to the input artifact file
    kind: optional kind override (report, backtest, research, audit, note)
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    SkillCandidate with provider_execution_disabled=True when dry_run=True
    """
    path = Path(input_path)
    text = _read_input_text(path)
    detected_kind = kind or _detect_kind(path)

    title = _generate_title(text, detected_kind)
    summary = _generate_static_summary(text, detected_kind, path.name)
    limitations = _generate_static_limitations(text)
    safety_notes = _generate_safety_notes(text)

    provenance = SkillProvenance(
        source_path=str(path),
        source_kind=detected_kind,
        workspace=str(workspace),
        provider_execution_disabled=True,
        static_fallback=True,
    )

    return SkillCandidate(
        title=title,
        summary=summary,
        kind=detected_kind,
        provenance=provenance,
        limitations=limitations,
        safety_notes=safety_notes,
        activation_policy="manual_only",
        status=SkillCandidateStatus.draft,
    )


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
    return "general"
