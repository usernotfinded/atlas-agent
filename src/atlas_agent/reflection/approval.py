"""Reflection approval workflow.

Manages state transitions for reflection artifacts:
draft -> pending_review -> approved/rejected -> archived

All operations are local. No provider or broker calls.
"""
from __future__ import annotations

from atlas_agent.reflection.models import ReflectionArtifact, ReflectionStatus
from atlas_agent.reflection.storage import save_artifact


def submit_for_review(
    artifact: ReflectionArtifact,
    *,
    actor: str = "cli:user",
    workspace: str = ".",
) -> ReflectionArtifact:
    """Submit a draft reflection for operator review."""
    if artifact.status != ReflectionStatus.draft:
        raise ValueError(
            f"Cannot submit reflection with status '{artifact.status.value}' for review. "
            "Only 'draft' reflections can be submitted."
        )
    artifact.record_transition(ReflectionStatus.pending_review, actor=actor)
    save_artifact(artifact, workspace=workspace)
    return artifact


def approve(
    artifact: ReflectionArtifact,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> ReflectionArtifact:
    """Approve a pending reflection."""
    if artifact.status != ReflectionStatus.pending_review:
        raise ValueError(
            f"Cannot approve reflection with status '{artifact.status.value}'. "
            "Only 'pending_review' reflections can be approved."
        )
    artifact.record_transition(
        ReflectionStatus.approved, actor=actor, reason=reason
    )
    save_artifact(artifact, workspace=workspace)
    return artifact


def reject(
    artifact: ReflectionArtifact,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> ReflectionArtifact:
    """Reject a pending reflection."""
    if artifact.status != ReflectionStatus.pending_review:
        raise ValueError(
            f"Cannot reject reflection with status '{artifact.status.value}'. "
            "Only 'pending_review' reflections can be rejected."
        )
    artifact.record_transition(
        ReflectionStatus.rejected, actor=actor, reason=reason
    )
    save_artifact(artifact, workspace=workspace)
    return artifact


def archive(
    artifact: ReflectionArtifact,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> ReflectionArtifact:
    """Archive an approved or rejected reflection."""
    if artifact.status not in (ReflectionStatus.approved, ReflectionStatus.rejected):
        raise ValueError(
            f"Cannot archive reflection with status '{artifact.status.value}'. "
            "Only 'approved' or 'rejected' reflections can be archived."
        )
    artifact.record_transition(
        ReflectionStatus.archived, actor=actor, reason=reason
    )
    save_artifact(artifact, workspace=workspace)
    return artifact
