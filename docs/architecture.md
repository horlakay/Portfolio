# Architecture

## Service Responsibilities

- `ingestion-service`: authentic edge for event intake, strict schema validation, idempotency tracking, and raw topic publication.
- `feature-service`: consumes raw events, persists event history, maintains account profile aggregates, and exposes low-latency feature lookup with Redis caching.
  - the lookup path explicitly computes features against historical state before the current event when that event has already been indexed, which avoids stream-ordering skew between consumers.
- `rule-engine`: evaluates deterministic fraud and security rules from YAML using a safe expression interpreter.
- `model-service`: serves active and candidate fraud models, returns risk score and lightweight contribution data, emits shadow divergence and drift signals, and exposes shadow summary, registry, and latest evaluation endpoints for analyst visibility.
- `decision-service`: orchestrates feature lookup, rule evaluation, and model inference into an allow/challenge/deny/manual-review outcome.
  - when feature lookup fails, it skips downstream scoring calls and falls back to a documented local heuristic path instead of trusting stale or zero-value feature inputs.
- `feedback-service`: stores analyst labels with actor identity, validates the referenced decision, enriches the label with decision context, and publishes feedback events for retraining and analytics.
- `analyst-console`: secure internal UI for triage, search, rule-hit inspection, feature context, and label submission.

## Data Flow

1. Clients submit login, password reset, device, and transaction events to `ingestion-service`.
2. `ingestion-service` validates the payload and writes an idempotency record before publishing to `sentinel.events.raw`.
3. `feature-service` consumes raw events to update event history and account profile state in PostgreSQL, then invalidates hot cache entries in Redis.
4. `decision-service` consumes the same raw topic for decision-worthy events or accepts synchronous scoring requests through `/v1/decisions/score`.
5. `decision-service` calls:
   - `feature-service` for real-time features,
   - `rule-engine` for deterministic control checks,
   - `model-service` for active and shadow risk scoring.
6. Final decisions are stored in PostgreSQL and published to `sentinel.events.decisions`.
7. Analysts inspect decisions in `analyst-console` and submit labels through `feedback-service`.
8. `feedback-service` stores the audit trail and publishes feedback to `sentinel.events.feedback`.

## Sync vs Async Boundaries

- Asynchronous:
  - Event ingestion to stream publication.
  - Feature aggregation from the raw topic.
  - Continuous decisioning from the raw topic.
  - Feedback publication for retraining.
- Synchronous:
  - Real-time decision API for front-door scoring.
  - Feature lookup for the current event.
  - Rule evaluation and model inference in the online path.

This split keeps the online decision path thin while still demonstrating event-driven architecture and replayable state updates.

## Storage Choices

- PostgreSQL:
  - authoritative persistence for ingested events, feature events, account profiles, decisions, and feedback.
  - chosen for operational familiarity, strong consistency, SQL analytics, and portfolio credibility.
- Redis:
  - hot feature cache for repeated account lookups.
  - tolerated as optional in degraded mode; a Redis outage increases latency but should not block decisions.
- Redpanda:
  - Kafka-compatible stream backbone for raw, decision, feedback, and dead-letter topics.
  - selected over a hand-rolled queue because it better reflects modern fintech eventing.

## Observability Pipeline

- OpenTelemetry:
  - FastAPI and HTTPX traces are emitted from every service to the local OpenTelemetry Collector.
  - Kafka producer and consumer spans are added manually so async stream hops remain visible in Tempo.
- Prometheus:
  - scrapes all application `/metrics` endpoints plus Redpanda, Promtail, Tempo, Loki, and the collector.
  - captures latency, outcome, cache, dependency, and broker health metrics.
- Loki:
  - ingests structured JSON logs from Docker via Promtail.
  - request IDs, trace IDs, account IDs, and event IDs stay queryable for incident triage.
- Tempo:
  - stores traces for synchronous API calls and async stream processing.
  - Grafana links traces to Loki logs by `trace_id`.

## Scaling Notes

- `ingestion-service`, `rule-engine`, `model-service`, `decision-service`, and `feedback-service` scale horizontally behind Kubernetes services.
- `feature-service` scales with consumer partitions and cache hit rate; Redis and Postgres are the primary bottlenecks to watch.
- `decision-service` is intentionally stateless outside its database writes and can scale on CPU or request concurrency.
- The shadow model path stays read-only, so candidate evaluation does not affect live decisions and can be disabled independently.
- Docker Compose health checks gate local startup so `decision-service` waits for feature, rule, model, Postgres, and Redpanda readiness before accepting traffic.

## Cloud Deployment Notes

- Terraform provisions the VPC, EKS cluster, shared ECR path, and artifact bucket.
- Helm is the authoritative application packaging layer for Kubernetes deployments.
- The chart expects PostgreSQL, Redis, and Kafka-compatible endpoints to be supplied per environment.
- Analyst traffic is intended to enter through an internal `LoadBalancer` Service by default, with Ingress left optional for clusters that already run an ingress controller.
