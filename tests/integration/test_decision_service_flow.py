from __future__ import annotations

from dataclasses import dataclass

import pytest

from decision_service.main import score_event
from sentinel_shared.config import CommonSettings
from sentinel_shared.schemas.decision import DecisionOutcome, RuleEvaluationResponse
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureLookupResponse, FeatureSnapshot
from sentinel_shared.schemas.model import ModelScoreResponse


class FeatureClient:
    async def lookup(self, event: EventEnvelope) -> FeatureLookupResponse:
        return FeatureLookupResponse(
            snapshot=FeatureSnapshot(
                failed_login_count_5m=4,
                new_device_flag=True,
                new_region_flag=True,
                session_anomaly_score=0.8,
            ),
            computed_at=event.timestamp,
        )


class RuleClient:
    async def evaluate(self, event: EventEnvelope, features: FeatureLookupResponse) -> RuleEvaluationResponse:
        return RuleEvaluationResponse(hits=[])


class ModelClient:
    async def score(self, event: EventEnvelope, features: FeatureLookupResponse) -> ModelScoreResponse:
        return ModelScoreResponse(
            risk_score=0.82,
            confidence=0.74,
            model_name="fraud-gbt",
            model_version="20260401090000",
            shadow_enabled=True,
            candidate_model_name="fraud-rf-shadow",
            candidate_risk_score=0.61,
            candidate_confidence=0.22,
            divergence=True,
            evaluated_at=event.timestamp,
        )


class FailingFeatureClient:
    async def lookup(self, event: EventEnvelope) -> FeatureLookupResponse:
        raise TimeoutError("simulated feature timeout")


class SpyRuleClient:
    def __init__(self) -> None:
        self.called = False

    async def evaluate(self, event: EventEnvelope, features: FeatureLookupResponse) -> RuleEvaluationResponse:
        self.called = True
        return RuleEvaluationResponse(hits=[])


class SpyModelClient:
    def __init__(self) -> None:
        self.called = False

    async def score(self, event: EventEnvelope, features: FeatureLookupResponse) -> ModelScoreResponse:
        self.called = True
        return ModelScoreResponse(
            risk_score=0.5,
            confidence=0.1,
            model_name="unused",
            model_version="unused",
            evaluated_at=event.timestamp,
        )


@dataclass
class FakeState:
    settings: CommonSettings
    feature_client: object
    rule_client: object
    model_client: object


@pytest.mark.asyncio
async def test_decision_service_challenges_from_model_signal() -> None:
    state = FakeState(
        settings=CommonSettings(),
        feature_client=FeatureClient(),
        rule_client=RuleClient(),
        model_client=ModelClient(),
    )
    decision = await score_event(
        state,
        EventEnvelope(
            event_type=EventType.LOGIN_ATTEMPT,
            user_id="user-1",
            account_id="acct-1",
        ),
    )
    assert decision.outcome == DecisionOutcome.CHALLENGE
    assert decision.active_model_name == "fraud-gbt"
    assert decision.candidate_model_name == "fraud-rf-shadow"
    assert decision.shadow_divergence is True
    assert decision.metadata["candidate_risk_score"] == 0.61
    assert decision.metadata["candidate_confidence"] == 0.22
    assert decision.metadata["scoring_mode"] == "ml_inference"
    assert decision.metadata["model_version"] == "20260401090000"
    assert decision.metadata["feature_source"] == "postgres"
    assert decision.metadata["feature_cache_hit"] is False
    assert decision.metadata["rule_hit_count"] == 0


@pytest.mark.asyncio
async def test_feature_failure_skips_downstream_model_and_rule_calls() -> None:
    rule_client = SpyRuleClient()
    model_client = SpyModelClient()
    state = FakeState(
        settings=CommonSettings(),
        feature_client=FailingFeatureClient(),
        rule_client=rule_client,
        model_client=model_client,
    )
    decision = await score_event(
        state,
        EventEnvelope(
            event_type=EventType.LOGIN_ATTEMPT,
            user_id="user-2",
            account_id="acct-2",
        ),
    )
    assert decision.degraded_mode is True
    assert rule_client.called is False
    assert model_client.called is False
    assert decision.dependency_status.feature_service == "TimeoutError"
    assert decision.dependency_status.rule_engine == "skipped_missing_features"
    assert decision.dependency_status.model_service == "skipped_missing_features"
    assert decision.metadata["scoring_mode"] == "heuristic_fallback"
    assert decision.metadata["feature_source"] == "degraded-defaults"
