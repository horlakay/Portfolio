from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class FeedbackLabel(StrEnum):
    CONFIRMED_FRAUD = "confirmed_fraud"
    FALSE_POSITIVE = "false_positive"
    SUSPICIOUS_UNCONFIRMED = "suspicious_unconfirmed"
    LEGITIMATE = "legitimate"


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: UUID = Field(default_factory=uuid4)
    decision_id: UUID
    label: FeedbackLabel
    notes: str | None = Field(default=None, max_length=2000)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class FeedbackDecisionContext(BaseModel):
    decision_id: UUID
    event_id: UUID
    account_id: str
    outcome: str
    risk_score: float
    confidence: float
    degraded_mode: bool
    decided_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRecord(FeedbackSubmission):
    actor_id: str
    actor_role: str
    decision_context: FeedbackDecisionContext
