# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/renderers.py
# PURPOSE: Renders a learning suggestion for a human (Markdown) or a machine (JSON).
#          Presentation only — nothing here decides anything.
# DEPS:    learning.models
# ==============================================================================

"""Markdown and JSON string renderers for learning suggestion output."""

# --- IMPORTS ---
from __future__ import annotations

import json

from atlas_agent.learning.models import LearningSuggestion


# ==============================================================================
# RENDERERS
# ==============================================================================


def render_markdown(suggestion: LearningSuggestion) -> str:
    """Render a learning suggestion as a human-friendly Markdown summary."""
    lines = [
        f"# Learning Suggestion: {suggestion.title}",
        "",
        f"**ID:** `{suggestion.suggestion_id}`",
        f"**Status:** {suggestion.status.value}",
        f"**Kind:** {suggestion.kind}",
        f"**Schema Version:** {suggestion.schema_version}",
        "",
        "## Summary",
        suggestion.summary or "No summary available.",
        "",
        "## Provenance",
        f"- **Generator Version:** {suggestion.provenance.generator_version}",
        f"- **Generated At:** {suggestion.provenance.generated_at}",
        f"- **Workspace:** {suggestion.provenance.workspace}",
    ]
    if suggestion.provenance.source_reflection_id:
        lines.append(f"- **Source Reflection ID:** {suggestion.provenance.source_reflection_id}")
    if suggestion.provenance.source_skill_id:
        lines.append(f"- **Source Skill ID:** {suggestion.provenance.source_skill_id}")
    if suggestion.provenance.source_candidate_id:
        lines.append(f"- **Source Candidate ID:** {suggestion.provenance.source_candidate_id}")
    if suggestion.provenance.source_path:
        lines.append(f"- **Source Path:** {suggestion.provenance.source_path}")
    if suggestion.provenance.source_kind:
        lines.append(f"- **Source Kind:** {suggestion.provenance.source_kind}")
    lines.append(f"- **Provider Execution Disabled:** {suggestion.provenance.provider_execution_disabled}")
    lines.append(f"- **Static Fallback:** {suggestion.provenance.static_fallback}")
    lines.extend(["", "## Evidence"])
    if suggestion.evidence:
        for item in suggestion.evidence:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Limitations"])
    if suggestion.limitations:
        for item in suggestion.limitations:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Safety Notes"])
    if suggestion.safety_notes:
        for item in suggestion.safety_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Recommended Next Step", suggestion.recommended_next_step or "None specified."])
    lines.extend(["", "## Execution Policy", f"- {suggestion.execution_policy}"])
    lines.extend(["", "## Audit"])
    lines.append(f"- **Created At:** {suggestion.audit.created_at}")
    if suggestion.audit.submitted_for_review_at:
        lines.append(f"- **Submitted For Review At:** {suggestion.audit.submitted_for_review_at}")
    if suggestion.audit.reviewed_at:
        lines.append(f"- **Reviewed At:** {suggestion.audit.reviewed_at}")
    if suggestion.audit.reviewed_by:
        lines.append(f"- **Reviewed By:** {suggestion.audit.reviewed_by}")
    if suggestion.audit.review_reason:
        lines.append(f"- **Review Reason:** {suggestion.audit.review_reason}")
    if suggestion.audit.archived_at:
        lines.append(f"- **Archived At:** {suggestion.audit.archived_at}")
    lines.extend(["", "## Disclaimer", suggestion.disclaimer])
    return "\n".join(lines)


def render_json_string(suggestion: LearningSuggestion) -> str:
    """Render a learning suggestion as a JSON string."""
    return json.dumps(suggestion.model_dump(mode="json"), indent=2, sort_keys=True, default=str)
