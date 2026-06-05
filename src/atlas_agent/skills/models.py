"""Skill candidate models.

Skill candidates are structured, reviewable artifacts derived from reflections
or local input files. They remain offline, do not call providers or brokers,
and require explicit human approval before promotion into the skill library.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SkillCandidateStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"
    promoted = "promoted"


class SkillProvenance(BaseModel):
    """Tracks where a skill candidate came from."""

    generator_version: str = "1.0.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_reflection_id: str | None = None
    source_path: str = ""
    source_kind: str = ""
    workspace: str = "."
    provider_execution_disabled: bool = True
    static_fallback: bool = True


class SkillAudit(BaseModel):
    """Tracks review/approval state transitions for skill candidates."""

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    submitted_for_review_at: str | None = None
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    archived_at: str | None = None
    promoted_at: str | None = None
    status_transitions: list[dict[str, Any]] = Field(default_factory=list)


class SkillCandidate(BaseModel):
    """A skill candidate artifact.

    Safe to serialize to JSON. Contains no secrets. Does not enable live trading.
    """

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: Literal["skill_candidate"] = "skill_candidate"
    schema_version: str = "1.0.0"
    status: SkillCandidateStatus = SkillCandidateStatus.draft
    title: str = ""
    summary: str = ""
    kind: str = "general"
    provenance: SkillProvenance = Field(default_factory=SkillProvenance)
    audit: SkillAudit = Field(default_factory=SkillAudit)
    limitations: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    activation_policy: Literal["manual_only", "disabled"] = "manual_only"
    disclaimer: str = (
        "This skill candidate is a research-only local artifact. It is not financial advice, "
        "not a trading instruction, and not automatically active. Operator review is required "
        "before any operational use. Provider execution and broker execution remain disabled "
        "by default."
    )

    def record_transition(
        self,
        new_status: SkillCandidateStatus,
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
        if new_status == SkillCandidateStatus.pending_review:
            self.audit.submitted_for_review_at = now
        elif new_status == SkillCandidateStatus.approved:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "approved"
        elif new_status == SkillCandidateStatus.rejected:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "rejected"
        elif new_status == SkillCandidateStatus.archived:
            self.audit.archived_at = now
        elif new_status == SkillCandidateStatus.promoted:
            self.audit.promoted_at = now


class SkillLibraryEntry(BaseModel):
    """A promoted skill in the local skill library."""

    skill_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: Literal["skill_library_entry"] = "skill_library_entry"
    schema_version: str = "1.0.0"
    title: str = ""
    summary: str = ""
    kind: str = "general"
    source_candidate_id: str = ""
    provenance: SkillProvenance = Field(default_factory=SkillProvenance)
    limitations: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    activation_policy: Literal["manual_only", "disabled"] = "manual_only"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    disclaimer: str = (
        "This skill is a research-only local artifact. It is not financial advice, "
        "not a trading instruction, and not automatically active. Operator review is required "
        "before any operational use."
    )
