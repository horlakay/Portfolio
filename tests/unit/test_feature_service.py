from __future__ import annotations

from datetime import UTC, datetime

from feature_service.main import derive_feature_snapshot
from sentinel_shared.schemas.events import EventEnvelope, GeoLocation


def test_feature_snapshot_marks_new_device_and_region() -> None:
    event = EventEnvelope(
        event_type="transaction_initiated",
        user_id="user-1",
        account_id="acct-1",
        timestamp=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        device_id="device-new",
        amount=1250,
        geolocation=GeoLocation(
            region="GB-LND",
            country="GB",
            city="London",
            latitude=51.5074,
            longitude=-0.1278,
        ),
    )
    snapshot = derive_feature_snapshot(
        {
            "known_devices": ["device-old"],
            "known_regions": ["US-NY"],
            "avg_txn_amount_30d": 250.0,
            "device_reuse_score": 2.0,
            "account_age_days": 15,
            "failed_login_count_5m": 2,
            "txn_velocity_10m": 1,
        },
        event,
    )
    assert snapshot.new_device_flag is True
    assert snapshot.new_region_flag is True
    assert snapshot.baseline_amount_deviation > 3.0
    assert snapshot.session_anomaly_score >= 0.8


def test_feature_snapshot_uses_previous_login_for_impossible_travel() -> None:
    event = EventEnvelope(
        event_type="login_attempt",
        user_id="user-1",
        account_id="acct-1",
        timestamp=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        device_id="device-1",
        geolocation=GeoLocation(
            region="GB-LND",
            country="GB",
            city="London",
            latitude=51.5074,
            longitude=-0.1278,
        ),
    )
    snapshot = derive_feature_snapshot(
        {
            "known_devices": ["device-1"],
            "known_regions": ["US-CA"],
            "last_successful_login_at": "2026-04-01T00:30:00+00:00",
            "last_login_latitude": 37.7749,
            "last_login_longitude": -122.4194,
        },
        event,
    )
    assert snapshot.impossible_travel_flag is True
