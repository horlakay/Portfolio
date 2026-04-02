# API Spec

SentinelStream exposes service-local health probes plus domain APIs for ingestion, real-time feature lookup, rule evaluation, model scoring, decisioning, and analyst feedback.

Shared sample payloads live under [data/samples](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples).

## Common Health Endpoints

Every service exposes:

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

Successful response:

```json
{
  "status": "ready",
  "service": "decision-service"
}
```

## Auth Notes

- analyst and admin APIs use JWT bearer auth
- local demo tokens can be minted by the internal scripts using the configured `JWT_SECRET`
- public edge APIs are rate limited:
  - `ingestion-service`: `120/minute`
  - `decision-service`: `60/minute`

## ingestion-service

Base URL: `http://localhost:8001`

- `POST /v1/events`
  - headers: optional `Idempotency-Key`
  - request: [login_attempt.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/login_attempt.json)
  - response: [event_ingest_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/event_ingest_response.json)
- `GET /v1/events/{event_id}`
  - response: [event_payload_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/event_payload_response.json)

Example:

```bash
curl -X POST http://localhost:8001/v1/events \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-login-001" \
  -d @data/samples/login_attempt.json
```

## feature-service

Base URL: `http://localhost:8002`

- `POST /v1/features/lookup`
  - request: [transaction_initiated.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/transaction_initiated.json)
  - response: [feature_lookup_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feature_lookup_response.json)
- `GET /v1/features/accounts/{account_id}`
  - auth: analyst/admin JWT
  - response: [feature_account_profile_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feature_account_profile_response.json)
- `POST /v1/admin/faults`
  - auth: admin JWT
  - request body:

```json
{
  "delay_ms": 120,
  "cache_enabled": true
}
```

## rule-engine

Base URL: `http://localhost:8003`

- `POST /v1/rules/evaluate`
  - request: [rule_evaluation_request.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/rule_evaluation_request.json)
  - response: [rule_evaluation_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/rule_evaluation_response.json)
- `GET /v1/rules`
  - auth: analyst/admin JWT
  - response: [rules_list_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/rules_list_response.json)
- `POST /v1/admin/rules/reload`
  - auth: admin JWT

## model-service

Base URL: `http://localhost:8004`

- `POST /v1/model/score`
  - request: [model_score_request.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/model_score_request.json)
  - response: [model_score_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/model_score_response.json)
- `GET /v1/model/metadata`
  - auth: analyst/admin JWT
  - response: [model_metadata_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/model_metadata_response.json)
- `GET /v1/model/evaluation/latest`
  - auth: analyst/admin JWT
  - response: [model_evaluation_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/model_evaluation_response.json)
- `GET /v1/model/registry`
  - auth: analyst/admin JWT
  - response: [model_registry_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/model_registry_response.json)
- `GET /v1/model/drift`
  - auth: analyst/admin JWT
  - response: [drift_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/drift_response.json)
- `GET /v1/model/shadow/summary`
  - auth: analyst/admin JWT
  - response: [shadow_summary_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/shadow_summary_response.json)
- `POST /v1/admin/faults`
  - auth: admin JWT
  - request body:

```json
{
  "delay_ms": 250,
  "error_rate": 0.25
}
```

- `POST /v1/admin/promote-shadow`
  - auth: admin JWT
- `POST /v1/admin/reload`
  - auth: admin JWT

Example:

```bash
curl -X POST http://localhost:8004/v1/model/score \
  -H "Content-Type: application/json" \
  -d @data/samples/model_score_request.json
```

## decision-service

Base URL: `http://localhost:8005`

- `POST /v1/decisions/score`
  - request: [decision_request.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/decision_request.json)
  - response: [decision_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/decision_response.json)
  - returns `400` when the event type is not eligible for decisioning
- `GET /v1/decisions`
  - auth: analyst/admin JWT
  - query params: `account_id`, `limit`
  - response: [decision_list_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/decision_list_response.json)
- `GET /v1/decisions/{decision_id}`
  - auth: analyst/admin JWT
  - response: [decision_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/decision_response.json)

Example:

```bash
curl -X POST http://localhost:8005/v1/decisions/score \
  -H "Content-Type: application/json" \
  -d @data/samples/decision_request.json
```

## feedback-service

Base URL: `http://localhost:8006`

- `POST /v1/feedback`
  - auth: analyst/admin JWT
  - request: [feedback_submission.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feedback_submission.json)
  - response: [feedback_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feedback_response.json)
  - returns `404` when the referenced decision does not exist
- `GET /v1/feedback/decisions/{decision_id}`
  - auth: analyst/admin JWT
  - response: [feedback_list_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feedback_list_response.json)
- `GET /v1/feedback`
  - auth: analyst/admin JWT
  - query params: `account_id`, `limit`
  - response: [feedback_list_response.json](C:/Users/OMEN/Desktop/kayode/SentinelStream/data/samples/feedback_list_response.json)

## Sample Authenticated Calls

```bash
curl http://localhost:8004/v1/model/registry \
  -H "Authorization: Bearer $ANALYST_JWT"
```

```bash
curl http://localhost:8006/v1/feedback?account_id=acct-1001&limit=10 \
  -H "Authorization: Bearer $ANALYST_JWT"
```
