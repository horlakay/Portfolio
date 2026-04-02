from __future__ import annotations

from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel_shared.logging import get_logger, get_request_id
from sentinel_shared.schemas.decision import RuleEvaluationRequest, RuleEvaluationResponse
from sentinel_shared.schemas.events import EventEnvelope
from sentinel_shared.schemas.features import FeatureLookupResponse
from sentinel_shared.schemas.model import ModelScoreRequest, ModelScoreResponse
from sentinel_shared.telemetry import (
    dependency_circuit_open_total,
    dependency_request_latency_seconds,
    dependency_requests_total,
)
from sentinel_shared.utils.resilience import AsyncCircuitBreaker, CircuitOpenError


class BaseServiceClient:
    def __init__(
        self, base_url: str, timeout_ms: int = 30, caller_service: str = "unknown"
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_ms / 1000)
        self._breaker = AsyncCircuitBreaker()
        self._base_url = base_url
        self._caller_service = caller_service
        self._target_service = urlparse(base_url).hostname or base_url
        self._logger = get_logger(f"{caller_service}.{self._target_service}")

    async def close(self) -> None:
        await self._client.aclose()

    @retry(wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1), stop=stop_after_attempt(3))
    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def _request() -> dict[str, Any]:
            request_id = get_request_id()
            headers = {"X-Request-ID": request_id} if request_id else {}
            response = await self._client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        started = perf_counter()
        try:
            result = await self._breaker.call(_request)
        except CircuitOpenError:
            dependency_circuit_open_total.labels(self._caller_service, self._target_service).inc()
            dependency_requests_total.labels(
                self._caller_service,
                self._target_service,
                path,
                "circuit_open",
            ).inc()
            self._logger.warning("dependency_circuit_open", path=path, base_url=self._base_url)
            raise
        except Exception as exc:
            dependency_requests_total.labels(
                self._caller_service,
                self._target_service,
                path,
                exc.__class__.__name__,
            ).inc()
            dependency_request_latency_seconds.labels(
                self._caller_service,
                self._target_service,
                path,
            ).observe(perf_counter() - started)
            self._logger.warning(
                "dependency_request_failed",
                path=path,
                base_url=self._base_url,
                error=str(exc),
                exception_type=exc.__class__.__name__,
            )
            raise
        dependency_requests_total.labels(
            self._caller_service,
            self._target_service,
            path,
            "success",
        ).inc()
        dependency_request_latency_seconds.labels(
            self._caller_service,
            self._target_service,
            path,
        ).observe(perf_counter() - started)
        return result


class FeatureServiceClient(BaseServiceClient):
    async def lookup(self, event: EventEnvelope) -> FeatureLookupResponse:
        payload = await self._post("/v1/features/lookup", event.model_dump(mode="json"))
        return FeatureLookupResponse.model_validate(payload)


class RuleEngineClient(BaseServiceClient):
    async def evaluate(
        self,
        event: EventEnvelope,
        features: FeatureLookupResponse,
    ) -> RuleEvaluationResponse:
        payload = await self._post(
            "/v1/rules/evaluate",
            RuleEvaluationRequest(event=event, features=features.snapshot).model_dump(mode="json"),
        )
        return RuleEvaluationResponse.model_validate(payload)


class ModelServiceClient(BaseServiceClient):
    async def score(
        self,
        event: EventEnvelope,
        features: FeatureLookupResponse,
    ) -> ModelScoreResponse:
        payload = await self._post(
            "/v1/model/score",
            ModelScoreRequest(event=event, features=features.snapshot).model_dump(mode="json"),
        )
        return ModelScoreResponse.model_validate(payload)
