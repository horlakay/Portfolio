from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sentinel_shared.schemas.events import EventEnvelope, EventType, GeoLocation


def test_event_validation_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(
            {
                "event_type": "login_attempt",
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "user_id": "u1",
                "account_id": "a1",
                "unexpected": "boom",
            },
        )


def test_event_validation_accepts_geolocation() -> None:
    event = EventEnvelope(
        event_type=EventType.LOGIN_ATTEMPT,
        timestamp=datetime.now(tz=UTC),
        user_id="u1",
        account_id="a1",
        geolocation=GeoLocation(region="US-NY", country="US", latitude=40.0, longitude=-73.0),
    )
    assert event.geolocation is not None
    assert event.geolocation.region == "US-NY"

