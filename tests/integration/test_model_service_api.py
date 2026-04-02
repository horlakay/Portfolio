from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel_shared.auth import Role, create_access_token
from sentinel_shared.config import CommonSettings
from model_service.main import app


def test_model_score_endpoint_returns_active_and_candidate_scores() -> None:
    with TestClient(app) as client:
        payload = {
            "event": {
                "event_type": "transaction_initiated",
                "user_id": "user-1",
                "account_id": "acct-1",
                "amount": 1800,
            },
            "features": {
                "failed_login_count_5m": 4,
                "new_device_flag": True,
                "baseline_amount_deviation": 3.5,
                "session_anomaly_score": 0.7,
            },
        }
        response = client.post("/v1/model/score", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert "risk_score" in body
        assert "candidate_risk_score" in body
        assert body["shadow_enabled"] is True


def test_shadow_summary_endpoint_returns_rollup() -> None:
    with TestClient(app) as client:
        token = create_access_token("analyst-1", Role.ANALYST, CommonSettings())
        response = client.get(
            "/v1/model/shadow/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "total_scores" in body
        assert "divergence_count" in body


def test_model_registry_endpoint_returns_active_and_candidate_metadata() -> None:
    with TestClient(app) as client:
        token = create_access_token("analyst-1", Role.ANALYST, CommonSettings())
        response = client.get(
            "/v1/model/registry",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["active_model"]["name"] == "fraud-gbt"
        assert body["candidate_model"]["name"] == "fraud-rf-shadow"


def test_model_evaluation_endpoint_returns_metrics_snapshot() -> None:
    with TestClient(app) as client:
        token = create_access_token("analyst-1", Role.ANALYST, CommonSettings())
        response = client.get(
            "/v1/model/evaluation/latest",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] > 0
        assert body["active"]["roc_auc"] >= 0.0
