# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/approval.py
# PURPOSE: The state machine a learning suggestion must walk before it counts.
#          There is NO transition from draft straight to accepted: a suggestion the
#          agent wrote about its own behaviour has to pass through a human.
# DEPS:    learning.models (the states), learning.storage (persistence)
# ==============================================================================

"""Learning suggestion approval workflow.

Manages state transitions for learning suggestions:
draft -> pending_review -> accepted/rejected -> archived

All operations are local. No provider or broker calls.
"""

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus
from atlas_agent.learning.storage import save_suggestion


def submit_for_review(
    suggestion: LearningSuggestion,
    *,
    actor: str = "cli:user",
    workspace: str = ".",
) -> LearningSuggestion:
    """Submit a draft learning suggestion for operator review."""
    if suggestion.status != SuggestionStatus.draft:
        raise ValueError(
            f"Cannot submit suggestion with status '{suggestion.status.value}' for review. "
            "Only 'draft' suggestions can be submitted."
        )
    suggestion.record_transition(SuggestionStatus.pending_review, actor=actor)
    save_suggestion(suggestion, workspace=workspace)
    return suggestion


def accept(
    suggestion: LearningSuggestion,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> LearningSuggestion:
    """Accept a pending learning suggestion."""
    if suggestion.status != SuggestionStatus.pending_review:
        raise ValueError(
            f"Cannot accept suggestion with status '{suggestion.status.value}'. "
            "Only 'pending_review' suggestions can be accepted."
        )
    suggestion.record_transition(
        SuggestionStatus.accepted, actor=actor, reason=reason
    )
    save_suggestion(suggestion, workspace=workspace)
    return suggestion


def reject(
    suggestion: LearningSuggestion,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> LearningSuggestion:
    """Reject a pending learning suggestion."""
    if suggestion.status != SuggestionStatus.pending_review:
        raise ValueError(
            f"Cannot reject suggestion with status '{suggestion.status.value}'. "
            "Only 'pending_review' suggestions can be rejected."
        )
    suggestion.record_transition(
        SuggestionStatus.rejected, actor=actor, reason=reason
    )
    save_suggestion(suggestion, workspace=workspace)
    return suggestion


def archive(
    suggestion: LearningSuggestion,
    *,
    actor: str = "cli:user",
    reason: str | None = None,
    workspace: str = ".",
) -> LearningSuggestion:
    """Archive an accepted or rejected learning suggestion."""
    if suggestion.status not in (
        SuggestionStatus.accepted,
        SuggestionStatus.rejected,
    ):
        raise ValueError(
            f"Cannot archive suggestion with status '{suggestion.status.value}'. "
            "Only 'accepted' or 'rejected' suggestions can be archived."
        )
    suggestion.record_transition(
        SuggestionStatus.archived, actor=actor, reason=reason
    )
    save_suggestion(suggestion, workspace=workspace)
    return suggestion
