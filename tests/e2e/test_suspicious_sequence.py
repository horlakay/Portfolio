from __future__ import annotations

from dataclasses import dataclass

import pytest
from decision_service.main import score_event
from sentinel_shared.schemas.decision import (
    DecisionOutcome,
    RuleEvaluationResponse,
    RuleHit,
    RuleSeverity,
)
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureLookupResponse, FeatureSnapshot
from sentinel_shared.schemas.model import ModelScoreResponse


class FakeFeatureClient:
    async def lookup(self, event: EventEnvelope) -> FeatureLookupResponse:
        return FeatureLookupResponse(
            snapshot=FeatureSnapshot(
                failed_login_count_5m=6,
                new_device_flag=True,
                password_reset_recent_flag=True,
                baseline_amount_deviation=6,
                session_anomaly_score=0.9,
            ),
            computed_at=event.timestamp,
        )


class FakeRuleClient:
    async def evaluate(
        self, event: EventEnvelope, features: FeatureLookupResponse
    ) -> RuleEvaluationResponse:
        return RuleEvaluationResponse(
            hits=[
                RuleHit(
                    rule_id="R006",
                    name="password_reset_then_high_value_transfer",
                    severity=RuleSeverity.CRITICAL,
                    decision=DecisionOutcome.DENY,
                    explanation="recent reset followed by transfer",
                ),
            ],
        )


class FakeModelClient:
    async def score(
        self, event: EventEnvelope, features: FeatureLookupResponse
    ) -> ModelScoreResponse:
        return ModelScoreResponse(
            risk_score=0.98,
            confidence=0.91,
            model_name="active",
            model_version="1",
            candidate_model_name="shadow",
            candidate_risk_score=0.87,
            divergence=False,
            evaluated_at=event.timestamp,
        )


@dataclass
class FakeState:
    settings: object
    feature_client: object
    rule_client: object
    model_client: object


@pytest.mark.asyncio
async def test_suspicious_sequence_denies_transaction() -> None:
    from sentinel_shared.config import CommonSettings

    state = FakeState(
        settings=CommonSettings(),
        feature_client=FakeFeatureClient(),
        rule_client=FakeRuleClient(),
        model_client=FakeModelClient(),
    )
    event = EventEnvelope(
        event_type=EventType.TRANSACTION_INITIATED,
        user_id="user-1",
        account_id="acct-1",
        amount=3200,
    )
    decision = await score_event(state, event)
    assert decision.outcome == DecisionOutcome.DENY
    assert any("Hard deny" in rationale for rationale in decision.rationale)
