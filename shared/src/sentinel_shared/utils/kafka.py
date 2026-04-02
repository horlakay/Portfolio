from __future__ import annotations

import json
from time import perf_counter
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaProducer
from opentelemetry.trace import SpanKind

from sentinel_shared.logging import get_logger
from sentinel_shared.telemetry import (
    broker_publish_failures_total,
    broker_publish_latency_seconds,
    get_tracer,
    inject_trace_headers,
    stream_events_published_total,
)

def dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, default=str).encode("utf-8")


class JsonProducer:
    def __init__(self, bootstrap_servers: str, service_name: str = "unknown") -> None:
        self._service_name = service_name
        self._logger = get_logger(f"{service_name}.kafka")
        self._tracer = get_tracer(f"{service_name}.kafka")
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda payload: dumps(payload),
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def send(self, topic: str, payload: dict[str, Any], key: str | None = None) -> None:
        started = perf_counter()
        with self._tracer.start_as_current_span(
            "kafka.publish",
            kind=SpanKind.PRODUCER,
        ) as span:
            message_headers = inject_trace_headers()
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination.name", topic)
            span.set_attribute("messaging.operation", "publish")
            if key:
                span.set_attribute("messaging.kafka.message_key", key)
            try:
                await self._producer.send_and_wait(
                    topic,
                    payload,
                    key=key.encode("utf-8") if key else None,
                    headers=message_headers,
                )
            except Exception as exc:
                broker_publish_failures_total.labels(
                    self._service_name,
                    topic,
                    exc.__class__.__name__,
                ).inc()
                broker_publish_latency_seconds.labels(
                    self._service_name,
                    topic,
                    "error",
                ).observe(perf_counter() - started)
                self._logger.exception(
                    "broker_publish_failed",
                    topic=topic,
                    exception_type=exc.__class__.__name__,
                    error=str(exc),
                )
                raise
        stream_events_published_total.labels(self._service_name, topic).inc()
        broker_publish_latency_seconds.labels(self._service_name, topic, "success").observe(
            perf_counter() - started,
        )

    async def publish_dead_letter(
        self,
        topic: str,
        service_name: str,
        reason: str,
        raw_payload: str,
    ) -> None:
        await self.send(
            topic,
            {
                "service": service_name,
                "reason": reason,
                "raw_payload": raw_payload,
                "published_at": datetime.now(tz=UTC).isoformat(),
            },
        )
