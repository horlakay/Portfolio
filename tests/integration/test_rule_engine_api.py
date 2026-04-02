from __future__ import annotations

from fastapi.testclient import TestClient
from rule_engine.main import app


def test_rule_engine_returns_hits_for_obvious_case() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/rules/evaluate",
        json={
            "event": {
                "event_type": "transaction_initiated",
                "user_id": "user-1",
                "account_id": "acct-1",
                "amount": 5000,
            },
            "features": {
                "new_device_flag": True,
                "baseline_amount_deviation": 5,
                "session_anomaly_score": 0.9,
            },
        },
    )
    assert response.status_code == 200
    assert len(response.json()["hits"]) >= 1
