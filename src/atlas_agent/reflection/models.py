"""Reflection artifact models.

Reflection artifacts are structured local records that analyze input artifacts
(reports, backtests, research, audit summaries, manual notes). They work fully
offline, do not call providers or brokers, and require operator review before
downstream use.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ReflectionStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class ReflectionInput(BaseModel):
    """Reference to the input artifact being reflected upon."""

    kind: Literal["report", "backtest", "research", "audit", "note", "unknown"]
    path: str
    description: str = ""
    input_hash: str = ""


class ReflectionOutput(BaseModel):
    """Structured output of the reflection process."""

    summary: str = ""
    observations: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    provider_execution_disabled: bool = True
    static_fallback: bool = True


class ProvenanceMetadata(BaseModel):
    """Tracks where the reflection came from."""

    generator_version: str = "1.0.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    input_artifact: ReflectionInput
    workspace: str = "."


class AuditMetadata(BaseModel):
    """Tracks review/approval state transitions."""

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    submitted_for_review_at: str | None = None
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    archived_at: str | None = None
    status_transitions: list[dict[str, Any]] = Field(default_factory=list)


class ReflectionArtifact(BaseModel):
    """A local reflection artifact.

    Safe to serialize to JSON. Contains no secrets. Does not enable live trading.
    """

    reflection_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: Literal["reflection"] = "reflection"
    schema_version: str = "1.0.0"
    status: ReflectionStatus = ReflectionStatus.draft
    provenance: ProvenanceMetadata
    audit: AuditMetadata = Field(default_factory=AuditMetadata)
    output: ReflectionOutput = Field(default_factory=ReflectionOutput)
    disclaimer: str = (
        "This reflection is a research-only local artifact. It is not financial advice, "
        "not a trading instruction, and not a performance guarantee. Operator review is "
        "required before any downstream use."
    )

    def record_transition(
        self,
        new_status: ReflectionStatus,
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.status = new_status
        self.audit.status_transitions.append(
            {
                "from": self.status.value if self.status != new_status else "",
                "to": new_status.value,
                "at": now,
                "actor": actor,
                "reason": reason or "",
            }
        )
        if new_status == ReflectionStatus.pending_review:
            self.audit.submitted_for_review_at = now
        elif new_status == ReflectionStatus.approved:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "approved"
        elif new_status == ReflectionStatus.rejected:
            self.audit.reviewed_at = now
            self.audit.reviewed_by = actor
            self.audit.review_reason = reason or "rejected"
        elif new_status == ReflectionStatus.archived:
            self.audit.archived_at = now
