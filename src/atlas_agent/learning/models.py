# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/models.py
# PURPOSE: The shape of a learning suggestion — the agent's proposal about how it
#          should change its own behaviour. This is the most delicate thing in the
#          system: an agent editing its own rules. Hence the state machine and the
#          mandatory human accept.
# DEPS:    pydantic (models)
# ==============================================================================

"""Learning suggestion models.

Learning suggestions are structured, reviewable artifacts derived from
reflections, skill candidates, approved skills, or local input files. They
remain offline, do not call providers or brokers, and require explicit human
review before any downstream use. Suggestions are advisory-only and never
auto-executed.
"""

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SuggestionStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    accepted = "accepted"
    rejected = "rejected"
    archived = "archived"


class SuggestionProvenance(BaseModel):
    """Tracks where a learning suggestion came from."""

    generator_version: str = "1.0.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_reflection_id: str | None = None
    source_skill_id: str | None = None
    source_candidate_id: str | None = None
    source_path: str = ""
    source_kind: str = ""
    workspace: str = "."
    provider_execution_disabled: bool = True
    static_fallback: bool = True


class SuggestionAudit(BaseModel):
    """Tracks review/approval state transitions for learning suggestions."""

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    submitted_for_review_at: str | None = None
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    archived_at: str | None = None
    status_transitions: list[dict[str, Any]] = Field(default_factory=list)


class LearningSuggestion(BaseModel):
    """A learning suggestion artifact.

    Safe to serialize to JSON. Contains no secrets. Does not enable live trading.
    Execution policy is advisory_only by default. No auto-execution.
    """

    suggestion_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: Literal["learning_suggestion"] = "learning_suggestion"
    schema_version: str = "1.0.0"
    status: SuggestionStatus = SuggestionStatus.draft
    title: str = ""
    summary: str = ""
    kind: str = "general"
    provenance: SuggestionProvenance = Field(default_factory=SuggestionProvenance)
    audit: SuggestionAudit = Field(default_factory=SuggestionAudit)
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""
    execution_policy: Literal["advisory_only", "disabled"] = "advisory_only"
    disclaimer: str = (
        "This learning suggestion is a research-only local artifact. It is not financial advice, "
        "not a trading instruction, and not automatically executable. Operator review is required "
        "before any operational use. Provider execution and broker execution remain disabled "
        "by default. Skills are not automatically activated."
    )

    def record_transition(
        self,
        new_status: SuggestionStatus,
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.audit.status_transitions.append(
            {
                "from": self.status.value,
                "to": new_status.value,
                "at": now,
                "actor": actor,
                "reason": reason or "",
            }
        )
        self.status = new_status
        if new_status == SuggestionStatus.pending_review:
            self.audit.submitted_for_review_at = now
        elif new_status == SuggestionStatus.accepted:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "accepted"
        elif new_status == SuggestionStatus.rejected:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "rejected"
        elif new_status == SuggestionStatus.archived:
            self.audit.archived_at = now
