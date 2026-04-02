from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from feedback_service.main import DecisionRecord, submit_feedback
from sentinel_shared.auth import Role, TokenClaims
from sentinel_shared.config import CommonSettings
from sentinel_shared.schemas.feedback import FeedbackLabel, FeedbackSubmission


class DummySession:
    def __init__(self, decision: DecisionRecord | None) -> None:
        self._decision = decision
        self.added = None

    async def get(self, model, key):
        _ = model, key
        return self._decision

    def add(self, row) -> None:
        self.added = row

    async def commit(self) -> None:
        return None


class DummyRequest:
    def __init__(self, state) -> None:
        self.app = type("App", (), {"state": type("State", (), {"container": state})()})()


@pytest.mark.asyncio
async def test_feedback_is_enriched_with_decision_context() -> None:
    decision = DecisionRecord(
        decision_id="11111111-1111-4111-8111-111111111111",
        event_id="22222222-2222-4222-8222-222222222222",
        account_id="acct-1",
        event_type="transaction_initiated",
        outcome="manual_review",
        risk_score=0.78,
        confidence=0.66,
        degraded_mode=False,
        decided_at=datetime.now(tz=UTC),
        payload={"metadata": {"candidate_risk_score": 0.51, "candidate_confidence": 0.18}},
    )
    state = SimpleNamespace(
        settings=CommonSettings(),
        producer=SimpleNamespace(send=AsyncMock()),
    )
    record = await submit_feedback(
        FeedbackSubmission(
            decision_id=decision.decision_id,
            label=FeedbackLabel.CONFIRMED_FRAUD,
            notes="Confirmed during integration test.",
        ),
        request=DummyRequest(state),
        claims=TokenClaims(
            sub="analyst-1",
            role=Role.ANALYST,
            iss="sentinelstream",
            aud="sentinelstream-analyst",
            exp=9999999999,
        ),
        session=DummySession(decision),
    )
    assert record.decision_context.account_id == "acct-1"
    assert record.decision_context.outcome == "manual_review"
    assert record.actor_id == "analyst-1"
    assert record.decision_context.metadata["candidate_confidence"] == 0.18


@pytest.mark.asyncio
async def test_feedback_rejects_missing_decision() -> None:
    state = SimpleNamespace(
        settings=CommonSettings(),
        producer=SimpleNamespace(send=AsyncMock()),
    )
    with pytest.raises(HTTPException) as exc:
        await submit_feedback(
            FeedbackSubmission(
                decision_id="99999999-9999-4999-8999-999999999999",
                label=FeedbackLabel.LEGITIMATE,
            ),
            request=DummyRequest(state),
            claims=TokenClaims(
                sub="analyst-1",
                role=Role.ANALYST,
                iss="sentinelstream",
                aud="sentinelstream-analyst",
                exp=9999999999,
            ),
            session=DummySession(None),
        )
    assert exc.value.status_code == 404
