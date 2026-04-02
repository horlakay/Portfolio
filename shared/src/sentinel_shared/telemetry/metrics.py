from __future__ import annotations

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

request_counter = Counter(
    "http_requests_total",
    "HTTP requests handled by SentinelStream services",
    ["service", "method", "path", "status"],
)
request_latency = Histogram(
    "request_latency_seconds",
    "HTTP request latency by service",
    ["service", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.3, 0.6),
)
active_http_requests = Gauge(
    "http_requests_in_flight",
    "HTTP requests currently in flight",
    ["service"],
)
decision_latency = Histogram(
    "decision_latency_seconds",
    "End-to-end decision latency",
    ["mode"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5),
)
decision_outcomes_total = Counter(
    "decision_outcomes_total",
    "Decision outcomes produced by the decision service",
    ["outcome", "degraded_mode"],
)
events_ingested_total = Counter(
    "events_ingested_total",
    "Accepted and replayed events seen by ingestion-service",
    ["event_type", "result"],
)
rule_hits_total = Counter("rule_hits_total", "Total number of rule hits", ["rule_name", "decision"])
model_score_distribution = Histogram(
    "model_score_distribution",
    "Observed model score distribution",
    ["model_name"],
    buckets=(0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.85, 0.95, 1.0),
)
shadow_model_divergence_total = Counter(
    "shadow_model_divergence_total",
    "Count of active-vs-shadow divergence events",
    ["active_model", "candidate_model"],
)
feature_lookup_latency_seconds = Histogram(
    "feature_lookup_latency_seconds",
    "Feature lookup latency",
    ["cache"],
    buckets=(0.001, 0.003, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2),
)
feature_cache_operations_total = Counter(
    "feature_cache_operations_total",
    "Feature cache operations by outcome",
    ["operation", "outcome"],
)
kafka_consumer_lag = Gauge(
    "kafka_consumer_lag",
    "Approximate consumer lag per service and topic",
    ["service", "topic"],
)
stream_events_published_total = Counter(
    "stream_events_published_total",
    "Messages published to the streaming backbone",
    ["service", "topic"],
)
broker_publish_latency_seconds = Histogram(
    "broker_publish_latency_seconds",
    "Latency for broker publish operations",
    ["service", "topic", "status"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
broker_publish_failures_total = Counter(
    "broker_publish_failures_total",
    "Broker publish failures",
    ["service", "topic", "error"],
)
dependency_requests_total = Counter(
    "dependency_requests_total",
    "Outbound dependency requests from services",
    ["caller", "target", "path", "status"],
)
dependency_request_latency_seconds = Histogram(
    "dependency_request_latency_seconds",
    "Outbound dependency request latency",
    ["caller", "target", "path"],
    buckets=(0.001, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.2, 0.5, 1.0),
)
dependency_circuit_open_total = Counter(
    "dependency_circuit_open_total",
    "Circuit breaker open events for downstream dependencies",
    ["caller", "target"],
)
dead_letter_events_total = Counter(
    "dead_letter_events_total",
    "Dead letter topic writes",
    ["service", "reason"],
)
feedback_labels_total = Counter(
    "feedback_labels_total",
    "Feedback labels submitted by analysts",
    ["label"],
)
drift_alerts_total = Counter(
    "drift_alerts_total",
    "Drift alerts triggered by feature monitors",
    ["feature_name"],
)


def mount_metrics(app: FastAPI) -> None:
    app.mount("/metrics", make_asgi_app())
