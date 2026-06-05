"""Reflection generator with dry-run/static fallback.

When provider execution is disabled (the default), the generator produces a
structured static reflection that clearly marks `provider_execution_disabled`.
No fake insights are invented. If input data is missing, the reflection says so.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from atlas_agent.reflection.models import (
    ReflectionArtifact,
    ReflectionInput,
    ReflectionOutput,
    ReflectionStatus,
    ProvenanceMetadata,
)


def _hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _read_input_text(path: Path) -> str:
    """Safely read input file text."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _detect_kind(path: Path) -> str:
    """Best-effort detection of input artifact kind from path/content."""
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
    return "unknown"


def _generate_static_observations(text: str, kind: str) -> list[str]:
    """Generate safe, non-fake observations from input text.

    These are structural observations, not invented insights.
    """
    observations: list[str] = []
    if not text:
        observations.append("No input data available.")
        return observations

    lines = text.splitlines()
    observations.append(f"Input contains {len(lines)} lines.")

    # Structural observations only
    header_count = sum(1 for line in lines if line.strip().startswith("#"))
    if header_count:
        observations.append(f"Contains {header_count} markdown headers.")

    if kind == "backtest":
        if "total_return_pct" in text.lower():
            observations.append("Backtest metrics present in input.")
        if "equity_curve" in text.lower() or "equity curve" in text.lower():
            observations.append("Equity curve data referenced.")
    elif kind == "report":
        if "portfolio" in text.lower():
            observations.append("Portfolio section present.")
        if "backtest" in text.lower():
            observations.append("Backtest section present.")
        if "risk" in text.lower():
            observations.append("Risk section present.")
    elif kind == "research":
        if "artifact" in text.lower():
            observations.append("Research artifacts referenced.")
    elif kind == "audit":
        if "event" in text.lower():
            observations.append("Audit events referenced.")

    if "disclaimer" in text.lower():
        observations.append("Input contains a disclaimer.")

    return observations


def _generate_static_questions(text: str, kind: str) -> list[str]:
    """Generate safe, open-ended review questions.

    These are generic review prompts, not fake analysis.
    """
    questions: list[str] = [
        "Does the input data cover the expected time period?",
        "Are all sections complete and free of placeholder content?",
    ]
    if kind == "backtest":
        questions.append("Are benchmark comparisons clearly labeled?")
        questions.append("Are risk metrics within expected bounds?")
    elif kind == "report":
        questions.append("Does the report accurately represent the underlying data?")
        questions.append("Are missing data sections clearly marked?")
    elif kind == "research":
        questions.append("Are research artifacts properly sourced and local?")
    elif kind == "audit":
        questions.append("Are all critical events captured in the audit log?")
    return questions


def generate_reflection(
    input_path: str | Path,
    *,
    kind: str | None = None,
    workspace: str | Path = ".",
    dry_run: bool = True,
) -> ReflectionArtifact:
    """Generate a reflection artifact from a local input file.

    Parameters
    ----------
    input_path: path to the input artifact file
    kind: optional kind override (report, backtest, research, audit, note)
    workspace: workspace root path
    dry_run: if True, use static fallback (default and recommended)

    Returns
    -------
    ReflectionArtifact with provider_execution_disabled=True when dry_run=True
    """
    path = Path(input_path)
    text = _read_input_text(path)
    detected_kind = kind or _detect_kind(path)
    file_hash = _hash_file(path)

    observations = _generate_static_observations(text, detected_kind)
    questions = _generate_static_questions(text, detected_kind)

    summary_parts: list[str] = []
    if not text:
        summary_parts.append("No input data available.")
    else:
        summary_parts.append(
            f"Static reflection on {detected_kind} artifact ({path.name})."
        )
        summary_parts.append(
            f"Provider execution is disabled. Reflection was generated using "
            f"a local static fallback."
        )

    output = ReflectionOutput(
        summary=" ".join(summary_parts),
        observations=observations,
        questions=questions,
        provider_execution_disabled=True,
        static_fallback=True,
    )

    provenance = ProvenanceMetadata(
        input_artifact=ReflectionInput(
            kind=detected_kind,  # type: ignore[arg-type]
            path=str(path),
            description=f"Local {detected_kind} artifact",
            input_hash=file_hash,
        ),
        workspace=str(workspace),
    )

    artifact = ReflectionArtifact(
        status=ReflectionStatus.draft,
        provenance=provenance,
        output=output,
    )

    return artifact
