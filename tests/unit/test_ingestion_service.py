from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ingestion_service.main import IngestedEvent, ingest_event
from sentinel_shared.config import CommonSettings
from sentinel_shared.schemas.events import EventEnvelope, EventType


class DummySession:
    def __init__(self, existing: IngestedEvent | None = None) -> None:
        self._existing = existing
        self.added = None
        self.committed = False

    async def scalar(self, *_args, **_kwargs):
        return self._existing

    def add(self, row) -> None:
        self.added = row

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False


class DummyRequest:
    def __init__(self, state) -> None:
        self.app = type("App", (), {"state": type("State", (), {"container": state})()})()


@pytest.mark.asyncio
async def test_ingest_event_returns_original_event_id_on_replay() -> None:
    existing = IngestedEvent(
        event_id="123e4567-e89b-12d3-a456-426614174000",
        idempotency_key="idem-1",
        event_type="login_attempt",
        account_id="acct-1",
        stored_at=datetime.now(tz=UTC),
        payload={},
    )
    settings = CommonSettings()
    state = SimpleNamespace(settings=settings, producer=SimpleNamespace(send=AsyncMock()))
    response = await ingest_event.__wrapped__(
        EventEnvelope(
            event_type=EventType.LOGIN_ATTEMPT,
            user_id="user-1",
            account_id="acct-1",
        ),
        request=DummyRequest(state),
        idempotency_key="idem-1",
        session=DummySession(existing=existing),
    )
    assert str(response.event_id) == existing.event_id
    assert response.idempotent_replay is True
