from __future__ import annotations

from decision_service.main import _combine_decision, _heuristic_score
from sentinel_shared.config import CommonSettings
from sentinel_shared.schemas.decision import DecisionOutcome, RuleHit, RuleSeverity
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureSnapshot


def test_hard_deny_rule_overrides_model() -> None:
    event = EventEnvelope(
        event_type=EventType.TRANSACTION_INITIATED, user_id="u1", account_id="a1", amount=5000
    )
    outcome, rationale = _combine_decision(
        event,
        risk_score=0.3,
        confidence=0.9,
        rule_hits=[
            RuleHit(
                rule_id="r1",
                name="critical",
                severity=RuleSeverity.CRITICAL,
                decision=DecisionOutcome.DENY,
                explanation="critical test",
            ),
        ],
        degraded=False,
        settings=CommonSettings(),
    )
    assert outcome == DecisionOutcome.DENY
    assert "Hard deny" in rationale[0]


def test_heuristic_score_increases_for_risky_features() -> None:
    event = EventEnvelope(event_type=EventType.LOGIN_ATTEMPT, user_id="u1", account_id="a1")
    score, confidence = _heuristic_score(
        event,
        FeatureSnapshot(
            failed_login_count_5m=6,
            new_device_flag=True,
            new_region_flag=True,
            impossible_travel_flag=True,
            session_anomaly_score=0.9,
        ),
        [],
    )
    assert score > 0.5
    assert confidence == 0.35
