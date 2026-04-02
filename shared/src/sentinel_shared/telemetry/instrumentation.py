from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from sentinel_shared.config import CommonSettings


@lru_cache(maxsize=16)
def _build_provider(service_name: str, environment: str, endpoint: str) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": environment,
            "service.namespace": "sentinelstream",
        },
    )
    provider = TracerProvider(resource=resource)
    sdk_disabled = os.getenv("OTEL_SDK_DISABLED", "").lower() in {"1", "true", "yes"}
    if not sdk_disabled and environment != "test" and endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
    return provider


def instrument_app(app: FastAPI, settings: CommonSettings) -> None:
    provider = _build_provider(
        settings.service_name,
        settings.environment,
        settings.otel_exporter_otlp_endpoint,
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    httpx_instrumentor = HTTPXClientInstrumentor()
    if not getattr(httpx_instrumentor, "is_instrumented_by_opentelemetry", False):
        httpx_instrumentor.instrument(tracer_provider=provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def inject_trace_headers(headers: dict[str, str] | None = None) -> list[tuple[str, bytes]]:
    carrier = dict(headers or {})
    inject(carrier)
    return [(key, value.encode("utf-8")) for key, value in carrier.items()]


def extract_trace_context(headers: list[tuple[str, bytes]] | None) -> Any:
    carrier = {key: value.decode("utf-8", errors="ignore") for key, value in (headers or [])}
    return extract(carrier)
