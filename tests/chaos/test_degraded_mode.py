from __future__ import annotations

from dataclasses import dataclass

import pytest
from decision_service.main import score_event
from sentinel_shared.config import CommonSettings
from sentinel_shared.schemas.decision import DecisionOutcome, RuleEvaluationResponse
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureLookupResponse, FeatureSnapshot


class HealthyFeatureClient:
    async def lookup(self, event: EventEnvelope) -> FeatureLookupResponse:
        return FeatureLookupResponse(
            snapshot=FeatureSnapshot(new_device_flag=True), computed_at=event.timestamp
        )


class EmptyRuleClient:
    async def evaluate(
        self, event: EventEnvelope, features: FeatureLookupResponse
    ) -> RuleEvaluationResponse:
        return RuleEvaluationResponse(hits=[])


class FailingModelClient:
    async def score(self, event: EventEnvelope, features: FeatureLookupResponse):
        raise TimeoutError("simulated timeout")


@dataclass
class FakeState:
    settings: CommonSettings
    feature_client: object
    rule_client: object
    model_client: object


@pytest.mark.asyncio
async def test_model_timeout_enters_degraded_mode() -> None:
    state = FakeState(
        settings=CommonSettings(),
        feature_client=HealthyFeatureClient(),
        rule_client=EmptyRuleClient(),
        model_client=FailingModelClient(),
    )
    decision = await score_event(
        state,
        EventEnvelope(event_type=EventType.LOGIN_ATTEMPT, user_id="user-1", account_id="acct-1"),
    )
    assert decision.degraded_mode is True
    assert decision.outcome in {DecisionOutcome.CHALLENGE, DecisionOutcome.ALLOW}
