# Runbook

## Service Objective

- Decision API availability target: `99.95%`
- Decision latency target:
  - p95 `< 75 ms`
  - p99 `< 150 ms`

## Primary Dashboards

- `System Overview`
- `Decision API Performance`
- `Fraud Alert Overview`
- `Stream Processing Health`
- `Drift and Model Behavior`

## Key Signals

Metrics:

- `http_requests_total`
- `request_latency_seconds`
- `http_requests_in_flight`
- `decision_latency_seconds`
- `decision_outcomes_total`
- `dependency_requests_total`
- `dependency_request_latency_seconds`
- `dependency_circuit_open_total`
- `feature_lookup_latency_seconds`
- `feature_cache_operations_total`
- `stream_events_published_total`
- `broker_publish_latency_seconds`
- `broker_publish_failures_total`
- `kafka_consumer_lag`
- `dead_letter_events_total`
- `rule_hits_total`
- `model_score_distribution`
- `shadow_model_divergence_total`
- `feedback_labels_total`
- `drift_alerts_total`

Logs:

- all services emit structured JSON to stdout
- logs include `service`, `request_id`, `trace_id`, `span_id`, `logger`, `message`
- Loki derived fields link `trace_id` directly to Tempo traces

Traces:

- FastAPI server spans on every service
- HTTPX client spans on service-to-service calls
- Kafka producer spans when publishing raw, decision, feedback, and DLQ events
- Kafka consumer spans in `feature-service` and `decision-service`

## Alert Matrix

- `HighHttpErrorRate`
  - meaning: elevated 5xx rate on a service
  - first look: `System Overview` dashboard, then Loki logs for the affected service
- `DecisionLatencyHigh`
  - meaning: decision p95 above 75ms
  - first look: `Decision API Performance`, especially feature lookup and dependency latency panels
- `DecisionDegradedModeSpike`
  - meaning: feature or model dependency issues are forcing heuristic fallback
  - first look: degraded outcome rate, dependency request failures, decision-service logs
- `ModelServiceUnavailable`
  - meaning: Prometheus cannot scrape model-service
  - first look: `/health/ready`, model-service logs, recent shadow promotion or reload
- `DependencyCircuitBreakerOpen`
  - meaning: downstream retries have tripped the circuit breaker
  - first look: dependency latency/errors and upstream service logs
- `FeatureCacheMissSpike`
  - meaning: cache hit ratio has degraded enough to risk p95 latency
  - first look: feature cache operation counts and Redis health
- `FeatureCacheErrors`
  - meaning: Redis operations are failing
  - first look: Redis container status, feature-service logs, feature lookup latency
- `BrokerPublishFailures`
  - meaning: one or more producers cannot publish to Redpanda
  - first look: stream health dashboard, Redpanda Console, producer logs
- `ConsumerLagHigh`
  - meaning: feature or decision consumers are behind
  - first look: `Stream Processing Health`, consumer logs, Redpanda health
- `DeadLetterQueueGrowth`
  - meaning: poison events or downstream failures are pushing payloads into the DLQ
  - first look: Redpanda Console topic contents and consumer logs
- `DriftThresholdExceeded`
  - meaning: live distributions are diverging from training baselines
  - first look: `Drift and Model Behavior`, model logs, latest evaluation/registry endpoints

## Investigation Workflow

1. Open the relevant Grafana dashboard and confirm whether the issue is isolated or system-wide.
2. Pivot to Loki logs for the implicated service.
3. Open a representative log line and follow its `trace_id` into Tempo.
4. Inspect the span timeline to identify whether the bottleneck is:
   - feature lookup
   - rule engine
   - model scoring
   - broker publish
   - persistence
5. Confirm whether the issue produced degraded decisions, DLQ traffic, or consumer lag.
6. Stabilize the platform first, then decide whether replay, rollback, or model promotion reversal is required.

## Common Failure Modes

### Model Timeout

Detection:

- `DecisionDegradedModeSpike`
- `ModelServiceUnavailable`
- elevated `dependency_requests_total{target="model-service",status!="success"}`
- decision logs with `message="model_service_failed"`

Failure simulation:

```bash
make chaos-model-timeout
```

Recovery:

```bash
make chaos-model-reset
docker compose logs model-service --tail=100
```

Notes:

- the decision service falls back to heuristic scoring when model inference fails
- verify `/v1/model/registry` and `/v1/model/evaluation/latest` before promoting or reloading artifacts

### Cache Failure or Cache Disabled

Detection:

- `FeatureCacheErrors`
- rising `feature_cache_operations_total{outcome="error"}`
- rising `feature_lookup_latency_seconds{cache="miss"}`
- feature-service logs with `feature_cache_get_failed`, `feature_cache_set_failed`, or `feature_cache_invalidation_failed`

Failure simulation:

```bash
make chaos-cache-disable
```

Hard outage simulation:

```bash
make chaos-redis-down
```

Recovery:

```bash
make chaos-feature-reset
make chaos-redis-up
docker compose logs feature-service --tail=100
```

Notes:

- the platform should remain functional with higher latency because Postgres remains authoritative

### Broker Issues

Detection:

- `BrokerPublishFailures`
- `ConsumerLagHigh`
- `stream_events_published_total` flattens while ingestion traffic continues
- producer logs with `broker_publish_failed`
- Redpanda Console shows stalled topics or unreachable broker

Failure simulation:

```bash
make chaos-broker-down
```

Recovery:

```bash
make chaos-broker-up
docker compose logs redpanda --tail=100
docker compose logs ingestion-service feature-service decision-service feedback-service --tail=100
```

Notes:

- producers should retry, and consumer lag should recover after broker restoration
- inspect DLQ before replaying anything generated during the outage window

### Malformed Event Poisoning

Detection:

- `DeadLetterQueueGrowth`
- consumer logs with validation errors
- Redpanda Console shows payloads in `sentinel.events.dlq`

Recovery:

1. identify the offending producer or bad schema deployment
2. stop or fix the producer
3. validate sample corrected payloads
4. replay only clean events

## Rollback Guidance

Application rollback:

- inspect release history:

```bash
helm history sentinelstream -n sentinelstream
```

- roll back the release:

```bash
helm rollback sentinelstream <revision> -n sentinelstream --wait
```

- if the issue is image-specific rather than config-specific, re-promote the previous known-good image tag through `promote-prod.yml`

Model rollback:

- restore prior active artifact and metadata
- use `/v1/admin/reload` after restoring the files

Feature/cache rollback:

- re-enable feature cache faults
- restore Redis and verify cache ops return to `success`

Broker rollback:

- restart Redpanda
- confirm publish failures stop and consumer lag trends down

Deployment rollback notes:

- `deploy.yml` and `promote-prod.yml` use `helm upgrade --atomic`, so failed upgrades auto-rollback
- if the release succeeded but performance regressed, prefer a manual Helm rollback to preserve an auditable revision history
- after rollback, verify:
  - `kubectl rollout status`
  - `/health/ready`
  - the latest benchmark artifact or smoke-test response

## Useful Commands

```bash
make logs
make chaos-model-timeout
make chaos-model-reset
make chaos-cache-disable
make chaos-feature-reset
make chaos-redis-down
make chaos-redis-up
make chaos-broker-down
make chaos-broker-up
```
