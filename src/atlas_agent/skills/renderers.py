"""Markdown and JSON string renderers for skill candidate output."""
from __future__ import annotations

import json

from atlas_agent.skills.models import SkillCandidate, SkillLibraryEntry


def render_markdown(candidate: SkillCandidate) -> str:
    """Render a skill candidate as a human-friendly Markdown summary."""
    lines = [
        f"# Skill Candidate: {candidate.title}",
        "",
        f"**ID:** `{candidate.candidate_id}`",
        f"**Status:** {candidate.status.value}",
        f"**Kind:** {candidate.kind}",
        f"**Schema Version:** {candidate.schema_version}",
        "",
        "## Summary",
        candidate.summary or "No summary available.",
        "",
        "## Provenance",
        f"- **Generator Version:** {candidate.provenance.generator_version}",
        f"- **Generated At:** {candidate.provenance.generated_at}",
        f"- **Workspace:** {candidate.provenance.workspace}",
    ]
    if candidate.provenance.source_reflection_id:
        lines.append(f"- **Source Reflection ID:** {candidate.provenance.source_reflection_id}")
    if candidate.provenance.source_path:
        lines.append(f"- **Source Path:** {candidate.provenance.source_path}")
    if candidate.provenance.source_kind:
        lines.append(f"- **Source Kind:** {candidate.provenance.source_kind}")
    lines.append(f"- **Provider Execution Disabled:** {candidate.provenance.provider_execution_disabled}")
    lines.append(f"- **Static Fallback:** {candidate.provenance.static_fallback}")
    lines.extend(["", "## Limitations"])
    if candidate.limitations:
        for item in candidate.limitations:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Safety Notes"])
    if candidate.safety_notes:
        for item in candidate.safety_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Activation Policy", f"- {candidate.activation_policy}"])
    lines.extend(["", "## Audit"])
    lines.append(f"- **Created At:** {candidate.audit.created_at}")
    if candidate.audit.submitted_for_review_at:
        lines.append(f"- **Submitted For Review At:** {candidate.audit.submitted_for_review_at}")
    if candidate.audit.reviewed_at:
        lines.append(f"- **Reviewed At:** {candidate.audit.reviewed_at}")
    if candidate.audit.reviewed_by:
        lines.append(f"- **Reviewed By:** {candidate.audit.reviewed_by}")
    if candidate.audit.review_reason:
        lines.append(f"- **Review Reason:** {candidate.audit.review_reason}")
    if candidate.audit.archived_at:
        lines.append(f"- **Archived At:** {candidate.audit.archived_at}")
    if candidate.audit.promoted_at:
        lines.append(f"- **Promoted At:** {candidate.audit.promoted_at}")
    lines.extend(["", "## Disclaimer", candidate.disclaimer])
    return "\n".join(lines)


def render_json_string(candidate: SkillCandidate) -> str:
    """Render a skill candidate as a JSON string."""
    return json.dumps(candidate.model_dump(mode="json"), indent=2, sort_keys=True, default=str)


def render_skill_markdown(entry: SkillLibraryEntry) -> str:
    """Render a skill library entry as a human-friendly Markdown summary."""
    lines = [
        f"# Skill: {entry.title}",
        "",
        f"**ID:** `{entry.skill_id}`",
        f"**Kind:** {entry.kind}",
        f"**Schema Version:** {entry.schema_version}",
        "",
        "## Summary",
        entry.summary or "No summary available.",
        "",
        "## Provenance",
        f"- **Generator Version:** {entry.provenance.generator_version}",
        f"- **Generated At:** {entry.provenance.generated_at}",
        f"- **Workspace:** {entry.provenance.workspace}",
    ]
    if entry.provenance.source_reflection_id:
        lines.append(f"- **Source Reflection ID:** {entry.provenance.source_reflection_id}")
    if entry.provenance.source_path:
        lines.append(f"- **Source Path:** {entry.provenance.source_path}")
    if entry.provenance.source_kind:
        lines.append(f"- **Source Kind:** {entry.provenance.source_kind}")
    lines.append(f"- **Provider Execution Disabled:** {entry.provenance.provider_execution_disabled}")
    lines.append(f"- **Static Fallback:** {entry.provenance.static_fallback}")
    lines.extend(["", "## Limitations"])
    if entry.limitations:
        for item in entry.limitations:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Safety Notes"])
    if entry.safety_notes:
        for item in entry.safety_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- None specified.")
    lines.extend(["", "## Activation Policy", f"- {entry.activation_policy}"])
    lines.extend(["", "## Disclaimer", entry.disclaimer])
    return "\n".join(lines)


def render_skill_json_string(entry: SkillLibraryEntry) -> str:
    """Render a skill library entry as a JSON string."""
    return json.dumps(entry.model_dump(mode="json"), indent=2, sort_keys=True, default=str)
