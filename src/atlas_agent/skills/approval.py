# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    skills/approval.py
# PURPOSE: The state machine for skill candidates. Note the extra terminal state
#          the other domains do not have: PROMOTED. That is the step where a
#          proposal stops being a document and starts influencing the agent.
# DEPS:    skills.models, skills.storage
# ==============================================================================

"""Skill candidate approval workflow.

Manages state transitions for skill candidates:
draft -> pending_review -> approved/rejected -> archived -> promoted

All operations are local. No provider or broker calls.
"""
from __future__ import annotations

from atlas_agent.skills.library import save_skill
from atlas_agent.skills.models import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillLibraryEntry,
)
from atlas_agent.skills.storage import save_candidate


def submit_for_review(
    candidate: SkillCandidate,
    *,
    actor: str = "cli:user",
    workspace: str = ".",
) -> SkillCandidate:
    """Submit a draft skill candidate for operator review."""
    if candidate.status != SkillCandidateStatus.draft:
        raise ValueError(
            f"Cannot submit candidate with status '{candidate.status.value}' for review. "
            "Only 'draft' candidates can be submitted."
        )
    candidate.record_transition(SkillCandidateStatus.pending_review, actor=actor)
    save_candidate(candidate, workspace=workspace)
    return candidate


def approve(
    candidate: SkillCandidate,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> SkillCandidate:
    """Approve a pending skill candidate."""
    if candidate.status != SkillCandidateStatus.pending_review:
        raise ValueError(
            f"Cannot approve candidate with status '{candidate.status.value}'. "
            "Only 'pending_review' candidates can be approved."
        )
    candidate.record_transition(
        SkillCandidateStatus.approved, actor=actor, reason=reason
    )
    save_candidate(candidate, workspace=workspace)
    return candidate


def reject(
    candidate: SkillCandidate,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> SkillCandidate:
    """Reject a pending skill candidate."""
    if candidate.status != SkillCandidateStatus.pending_review:
        raise ValueError(
            f"Cannot reject candidate with status '{candidate.status.value}'. "
            "Only 'pending_review' candidates can be rejected."
        )
    candidate.record_transition(
        SkillCandidateStatus.rejected, actor=actor, reason=reason
    )
    save_candidate(candidate, workspace=workspace)
    return candidate


def archive(
    candidate: SkillCandidate,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> SkillCandidate:
    """Archive an approved or rejected skill candidate."""
    if candidate.status not in (
        SkillCandidateStatus.approved,
        SkillCandidateStatus.rejected,
    ):
        raise ValueError(
            f"Cannot archive candidate with status '{candidate.status.value}'. "
            "Only 'approved' or 'rejected' candidates can be archived."
        )
    candidate.record_transition(
        SkillCandidateStatus.archived, actor=actor, reason=reason
    )
    save_candidate(candidate, workspace=workspace)
    return candidate


def promote_to_library(
    candidate: SkillCandidate,
    *,
    actor: str = "cli:user",
    workspace: str = ".",
) -> SkillLibraryEntry:
    """Promote an approved skill candidate into the skill library.

    Only approved candidates can be promoted.
    """
    if candidate.status != SkillCandidateStatus.approved:
        raise ValueError(
            f"Cannot promote candidate with status '{candidate.status.value}'. "
            "Only 'approved' candidates can be promoted."
        )
    candidate.record_transition(
        SkillCandidateStatus.promoted, actor=actor, reason="promoted_to_library"
    )
    save_candidate(candidate, workspace=workspace)

    entry = SkillLibraryEntry(
        title=candidate.title,
        summary=candidate.summary,
        kind=candidate.kind,
        source_candidate_id=candidate.candidate_id,
        provenance=candidate.provenance,
        limitations=candidate.limitations,
        safety_notes=candidate.safety_notes,
        activation_policy=candidate.activation_policy,
    )
    save_skill(entry, workspace=workspace)
    return entry
