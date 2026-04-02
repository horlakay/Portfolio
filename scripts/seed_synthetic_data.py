from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx


def build_event(index: int) -> dict:
    base_time = datetime.now(tz=UTC) - timedelta(minutes=60 - index)
    event_type = random.choice(["login_attempt", "transaction_initiated", "password_reset"])
    payload = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "timestamp": base_time.isoformat(),
        "user_id": f"user-{index % 50}",
        "account_id": f"acct-{index % 50}",
        "session_id": f"sess-{uuid4()}",
        "device_id": f"device-{index % 20}",
        "ip_address": f"198.51.100.{(index % 200) + 1}",
        "geolocation": {
            "region": random.choice(["US-NY", "US-CA", "GB-LND", "NG-LA"]),
            "country": random.choice(["US", "GB", "NG"]),
            "city": random.choice(["New York", "San Francisco", "London", "Lagos"]),
            "latitude": random.choice([40.7128, 37.7749, 51.5074, 6.5244]),
            "longitude": random.choice([-74.0060, -122.4194, -0.1278, 3.3792])
        },
        "metadata": {
            "auth_result": random.choice(["success", "failure"]) if event_type == "login_attempt" else None,
            "mfa_present": bool(random.getrandbits(1))
        }
    }
    if event_type == "transaction_initiated":
        payload["amount"] = round(random.uniform(25, 3500), 2)
        payload["currency"] = "USD"
    return payload


async def main() -> None:
    ingestion_url = os.environ.get("INGESTION_SERVICE_URL", "http://ingestion-service:8001")
    async with httpx.AsyncClient(base_url=ingestion_url, timeout=10.0) as client:
        for index in range(100):
            payload = build_event(index)
            response = await client.post(
                "/v1/events",
                json=payload,
                headers={"Idempotency-Key": f"seed-{index}"},
            )
            response.raise_for_status()
    print("seeded 100 synthetic events")


if __name__ == "__main__":
    asyncio.run(main())

