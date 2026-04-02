# System Design

## Why This Architecture

SentinelStream uses a hybrid synchronous + event-driven design because fraud systems typically need both:

- immediate scoring for customer-facing flows such as logins and transfers,
- replayable event history for feature engineering, incident investigation, and model iteration.

The repository favors a practical service split rather than maximal microservice decomposition. Each service owns a clear domain and can be reasoned about independently in interviews, but the overall system remains small enough to run locally.

## Key Design Decisions

- Hybrid rule + ML decisioning:
  - rules handle hard policy controls and auditability.
  - ML handles behavioral outliers and blended risk signals.
- Stream-first feature updates:
  - lets the system replay history and model late-arriving events cleanly.
  - feature lookup excludes the in-flight event when it has already been consumed, which prevents current-event contamination of velocity and new-device checks.
- Shared Python runtime primitives:
  - keeps observability, auth, schemas, and resilience patterns consistent across services.
- Correlated telemetry by default:
  - request IDs, trace IDs, and structured JSON logs are emitted consistently, and Kafka producer/consumer spans keep async hops visible in the trace graph.
- Shadow model evaluation:
  - demonstrates safe model iteration without production blast radius.
  - active and candidate artifacts publish registry and evaluation metadata so analysts can inspect versions, metrics, and promotion state without shell access.
- Deliberate degraded mode:
  - if the feature path is unavailable, the decision service skips downstream model and rule calls and uses a documented heuristic fallback.
  - if the model path is unavailable but features are present, the system falls back to rules plus heuristic scoring rather than failing open.

## Tradeoffs

- PostgreSQL instead of a dedicated online feature store:
  - simplifies local development and portfolio readability.
  - acceptable here because Redis absorbs hot reads and the scale target is demo-grade, not hyperscale.
- Startup-time table creation instead of a full migration system:
  - keeps the local path frictionless.
  - for production hardening, Alembic or Flyway would be the next upgrade.
- Server-rendered analyst console instead of a heavier SPA:
  - reduces front-end overhead.
  - still provides realistic internal tooling and secure access patterns.
- Application-tier deployment on EKS with externally supplied data-plane endpoints:
  - keeps the repo focused on platform delivery and service design instead of hiding the application behind managed-service magic.
  - local Docker Compose still demonstrates the full end-to-end stack when a self-contained demo is more useful than a cloud environment.

## Future Improvements

- replace startup schema creation with migrations and schema drift checks.
- add managed feature backfill jobs and late-event correction workflows.
- introduce request signing or mTLS for service-to-service auth.
- add model registry promotion workflow with approval policy and signed artifacts.
- expand drift detection from mean-based PSI approximations to per-bucket distribution tracking.
