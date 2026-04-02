from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
from sentinel_shared.auth import Role, create_access_token
from sentinel_shared.config import CommonSettings

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


async def post_json(client: httpx.AsyncClient, path: str, payload: dict, headers: dict | None = None) -> None:
    response = await client.post(path, json=payload, headers=headers or {})
    response.raise_for_status()
    print(f"{path} -> {response.status_code}")
    print(response.text)


async def main() -> None:
    settings = CommonSettings()
    ingestion_url = os.environ.get("INGESTION_SERVICE_URL", "http://ingestion-service:8001")
    decision_url = os.environ.get("DECISION_SERVICE_URL", "http://decision-service:8005")
    feedback_url = os.environ.get("FEEDBACK_SERVICE_URL", "http://feedback-service:8006")
    feature_url = os.environ.get("FEATURE_SERVICE_URL", "http://feature-service:8002")
    model_url = os.environ.get("MODEL_SERVICE_URL", "http://model-service:8004")
    login = json.loads((SAMPLES / "login_attempt.json").read_text(encoding="utf-8"))
    reset = json.loads((SAMPLES / "password_reset.json").read_text(encoding="utf-8"))
    transaction = json.loads((SAMPLES / "transaction_initiated.json").read_text(encoding="utf-8"))
    analyst_token = create_access_token("demo-analyst", Role.ANALYST, settings)
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    async with httpx.AsyncClient(base_url=ingestion_url, timeout=10.0) as ingestion_client:
        await post_json(ingestion_client, "/v1/events", login, {"Idempotency-Key": "demo-login-1"})
        await post_json(ingestion_client, "/v1/events", reset, {"Idempotency-Key": "demo-reset-1"})
        await post_json(ingestion_client, "/v1/events", transaction, {"Idempotency-Key": "demo-txn-1"})

    await asyncio.sleep(2)

    async with httpx.AsyncClient(base_url=decision_url, timeout=10.0) as decision_client:
        response = await decision_client.post("/v1/decisions/score", json={"event": transaction})
        response.raise_for_status()
        scored = response.json()
        print("decision ->", response.status_code)
        print(json.dumps(scored, indent=2))

        recent = await decision_client.get(
            "/v1/decisions",
            params={"account_id": transaction["account_id"], "limit": 5},
            headers=analyst_headers,
        )
        recent.raise_for_status()
        recent_decisions = recent.json()
        print("recent decisions ->")
        print(json.dumps(recent_decisions, indent=2))

    decision_id = recent_decisions[0]["decision_id"]

    async with httpx.AsyncClient(base_url=feedback_url, timeout=10.0) as feedback_client:
        feedback_response = await feedback_client.post(
            "/v1/feedback",
            json={
                "decision_id": decision_id,
                "label": "suspicious_unconfirmed",
                "notes": "Demo analyst label for recruiter walkthrough.",
            },
            headers=analyst_headers,
        )
        feedback_response.raise_for_status()
        print("feedback ->")
        print(feedback_response.text)

    async with httpx.AsyncClient(base_url=feature_url, timeout=10.0) as feature_client:
        profile = await feature_client.get(
            f"/v1/features/accounts/{transaction['account_id']}",
            headers=analyst_headers,
        )
        profile.raise_for_status()
        print("feature profile ->")
        print(profile.text)

    async with httpx.AsyncClient(base_url=model_url, timeout=10.0) as model_client:
        evaluation = await model_client.get(
            "/v1/model/evaluation/latest",
            headers=analyst_headers,
        )
        evaluation.raise_for_status()
        print("latest model evaluation ->")
        print(evaluation.text)

        registry = await model_client.get(
            "/v1/model/registry",
            headers=analyst_headers,
        )
        registry.raise_for_status()
        print("model registry ->")
        print(registry.text)

        shadow_summary = await model_client.get(
            "/v1/model/shadow/summary",
            headers=analyst_headers,
        )
        shadow_summary.raise_for_status()
        print("shadow summary ->")
        print(shadow_summary.text)


if __name__ == "__main__":
    asyncio.run(main())
