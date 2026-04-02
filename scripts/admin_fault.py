from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from sentinel_shared.auth import Role, create_access_token
from sentinel_shared.config import CommonSettings


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["model", "feature"], required=True)
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--error-rate", type=float, default=0.0)
    parser.add_argument("--cache-enabled", choices=["true", "false"], default="true")
    args = parser.parse_args()

    base_url = (
        os.environ.get("MODEL_SERVICE_URL", "http://model-service:8004")
        if args.target == "model"
        else os.environ.get("FEATURE_SERVICE_URL", "http://feature-service:8002")
    )
    settings = CommonSettings()
    token = os.environ.get("ADMIN_BEARER_TOKEN") or create_access_token("ops-admin", Role.ADMIN, settings)
    payload = {"delay_ms": args.delay_ms, "cache_enabled": args.cache_enabled == "true"}
    if args.target == "model":
        payload = {"delay_ms": args.delay_ms, "error_rate": args.error_rate}

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        response = await client.post(
            "/v1/admin/faults",
            json=payload,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        response.raise_for_status()
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
