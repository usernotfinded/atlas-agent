"""Markdown renderer for reflection artifacts."""
from __future__ import annotations

from atlas_agent.reflection.models import ReflectionArtifact


def render_markdown(artifact: ReflectionArtifact) -> str:
    """Render a reflection artifact as Markdown."""
    lines: list[str] = []

    lines.append(f"# Reflection: {artifact.reflection_id}")
    lines.append("")
    lines.append(f"**Status:** {artifact.status.value}")
    lines.append(f"**Schema Version:** {artifact.schema_version}")
    lines.append(f"**Generated:** {artifact.provenance.generated_at}")
    lines.append("")

    # Input provenance
    inp = artifact.provenance.input_artifact
    lines.append("## Input Artifact")
    lines.append("")
    lines.append(f"- **Kind:** {inp.kind}")
    lines.append(f"- **Path:** {inp.path}")
    if inp.description:
        lines.append(f"- **Description:** {inp.description}")
    if inp.input_hash:
        lines.append(f"- **Hash:** {inp.input_hash}")
    lines.append("")

    # Output
    out = artifact.output
    lines.append("## Reflection Output")
    lines.append("")
    lines.append(f"**Summary:** {out.summary}")
    lines.append("")

    if out.observations:
        lines.append("### Observations")
        lines.append("")
        for obs in out.observations:
            lines.append(f"- {obs}")
        lines.append("")

    if out.questions:
        lines.append("### Review Questions")
        lines.append("")
        for q in out.questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append(f"- **Provider Execution Disabled:** {'yes' if out.provider_execution_disabled else 'no'}")
    lines.append(f"- **Static Fallback:** {'yes' if out.static_fallback else 'no'}")
    lines.append("")

    # Audit
    audit = artifact.audit
    lines.append("## Audit Metadata")
    lines.append("")
    lines.append(f"- **Created:** {audit.created_at}")
    if audit.submitted_for_review_at:
        lines.append(f"- **Submitted for Review:** {audit.submitted_for_review_at}")
    if audit.reviewed_at:
        lines.append(f"- **Reviewed:** {audit.reviewed_at}")
    if audit.reviewed_by:
        lines.append(f"- **Reviewed By:** {audit.reviewed_by}")
    if audit.review_reason:
        lines.append(f"- **Review Reason:** {audit.review_reason}")
    if audit.archived_at:
        lines.append(f"- **Archived:** {audit.archived_at}")

    if audit.status_transitions:
        lines.append("")
        lines.append("### Status Transitions")
        lines.append("")
        lines.append("| From | To | At | Actor | Reason |")
        lines.append("| --- | --- | --- | --- | --- |")
        for t in audit.status_transitions:
            lines.append(
                f"| {t.get('from', '')} | {t.get('to', '')} | {t.get('at', '')} | "
                f"{t.get('actor', '')} | {t.get('reason', '')} |"
            )
    lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append(f"*{artifact.disclaimer}*")
    lines.append("")

    return "\n".join(lines)
