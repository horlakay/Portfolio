from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .events import EventEnvelope
from .features import FeatureSnapshot


class RuleSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    CHALLENGE = "challenge"
    DENY = "deny"
    MANUAL_REVIEW = "manual_review"


class RuleHit(BaseModel):
    rule_id: str
    name: str
    severity: RuleSeverity
    decision: DecisionOutcome
    explanation: str


class RuleEvaluationRequest(BaseModel):
    event: EventEnvelope
    features: FeatureSnapshot


class RuleEvaluationResponse(BaseModel):
    hits: list[RuleHit] = Field(default_factory=list)


class ModelContribution(BaseModel):
    feature_name: str
    contribution: float


class DependencyStatus(BaseModel):
    feature_service: str = "ok"
    rule_engine: str = "ok"
    model_service: str = "ok"


class DecisionRequest(BaseModel):
    event: EventEnvelope


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    account_id: str
    outcome: DecisionOutcome
    risk_score: float
    confidence: float
    rationale: list[str]
    rule_hits: list[RuleHit] = Field(default_factory=list)
    feature_snapshot: FeatureSnapshot
    active_model_name: str | None = None
    candidate_model_name: str | None = None
    shadow_divergence: bool = False
    degraded_mode: bool = False
    dependency_status: DependencyStatus = Field(default_factory=DependencyStatus)
    contributions: list[ModelContribution] = Field(default_factory=list)
    decided_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionRecordSummary(BaseModel):
    decision_id: UUID
    event_id: UUID
    account_id: str
    event_type: str
    outcome: DecisionOutcome
    risk_score: float
    confidence: float
    degraded_mode: bool
    decided_at: datetime

