from __future__ import annotations

from decision_service.main import app as decision_app
from ingestion_service.main import app as ingestion_app


def test_public_services_have_rate_limiter_configured() -> None:
    assert getattr(ingestion_app.state, "limiter", None) is not None
    assert getattr(decision_app.state, "limiter", None) is not None

