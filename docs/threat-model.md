# Threat Model

## Assets

- customer authentication events
- transfer and transaction events
- decision records and analyst annotations
- model artifacts and evaluation metadata
- JWT secrets and deployment credentials
- observability data that may contain sensitive operational context

## Actors

- external attackers attempting account takeover or fraudulent transfers
- abusive API clients replaying or flooding events
- malicious insiders misusing analyst access
- curious developers accidentally exposing secrets or PII through logs
- adversaries attempting model evasion with low-and-slow behavior

## Trust Boundaries

- public clients to `ingestion-service`
- internal service-to-service HTTP boundaries
- Kafka topic boundaries between producers and consumers
- analyst/admin console access boundary
- deployment boundary between local Docker and cloud Kubernetes

## Abuse Scenarios and Mitigations

### Account Takeover

- Scenario: attacker performs repeated failed logins, triggers password reset, then initiates a high-value transfer.
- Mitigations:
  - rules for failed logins plus recent password reset
  - anomaly features for new device, new region, impossible travel, and amount deviation
  - manual review and deny pathways

### Replay or Duplicate Event Submission

- Scenario: clients retry aggressively or a malicious actor replays a prior transaction event.
- Mitigations:
  - explicit idempotency key support
  - ingestion event record keyed by idempotency key
  - event ID uniqueness inside downstream consumers

### API Abuse

- Scenario: attackers flood the ingestion or scoring API to degrade service.
- Mitigations:
  - strict schema validation
  - intended rate limiting at ingress or API gateway
  - decoupled streaming layer for backpressure
  - dead-letter handling for poison events

### Insider Misuse of Analyst Tooling

- Scenario: analysts over-label, tamper with decisions, or explore records beyond need-to-know.
- Mitigations:
  - JWT-based analyst/admin separation
  - audit logging for feedback submission and admin actions
  - read-only decision inspection with separate label API

### Model Evasion

- Scenario: attackers shape activity to stay below deterministic thresholds.
- Mitigations:
  - ML scoring over blended behavioral features
  - shadow model comparison to test alternate decision boundaries
  - drift reporting to surface changing live distributions

### Sensitive Data Exposure Through Logs

- Scenario: IPs, tokens, or sensitive metadata leak into operational logs.
- Mitigations:
  - structured logging with field masking
  - no hardcoded secrets
  - explicit documentation that production deployments should route secrets through Kubernetes Secrets or AWS Secrets Manager

