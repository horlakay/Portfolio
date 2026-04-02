from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter

from aiokafka import AIOKafkaConsumer
from fastapi import Depends, FastAPI, HTTPException, Request
from opentelemetry.trace import SpanKind
from sentinel_shared.auth import Role, require_roles
from sentinel_shared.clients import FeatureServiceClient, ModelServiceClient, RuleEngineClient
from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import bind_log_context, clear_log_context, get_logger
from sentinel_shared.schemas.decision import (
    DecisionOutcome,
    DecisionRecordSummary,
    DecisionRequest,
    DecisionResponse,
    DependencyStatus,
    ModelContribution,
    RuleHit,
)
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureLookupResponse, FeatureSnapshot
from sentinel_shared.telemetry import (
    dead_letter_events_total,
    decision_latency,
    decision_outcomes_total,
    extract_trace_context,
    get_tracer,
    kafka_consumer_lag,
)
from sentinel_shared.utils.database import create_async_engine_and_session
from sentinel_shared.utils.fastapi import build_app
from sentinel_shared.utils.kafka import JsonProducer
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import JSON, Boolean, DateTime, Float, String, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
tracer = get_tracer(__name__)


class Base(DeclarativeBase):
    pass


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    risk_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    degraded_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class AppState:
    def __init__(self, settings: CommonSettings) -> None:
        self.settings = settings
        self.engine, self.session_factory = create_async_engine_and_session(settings.database_url)
        self.producer = JsonProducer(
            settings.kafka_bootstrap_servers, service_name=settings.service_name
        )
        self.consumer = AIOKafkaConsumer(
            settings.raw_events_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="decision-service",
            auto_offset_reset="earliest",
            value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
        )
        self.feature_client = FeatureServiceClient(
            settings.feature_service_url,
            settings.feature_timeout_ms,
            caller_service=settings.service_name,
        )
        self.rule_client = RuleEngineClient(
            settings.rule_engine_url,
            settings.rule_timeout_ms,
            caller_service=settings.service_name,
        )
        self.model_client = ModelServiceClient(
            settings.model_service_url,
            settings.model_timeout_ms,
            caller_service=settings.service_name,
        )
        self.consumer_task: asyncio.Task | None = None


def _empty_features() -> FeatureLookupResponse:
    return FeatureLookupResponse(
        snapshot=FeatureSnapshot(),
        computed_at=datetime.now(tz=UTC),
        cache_hit=False,
        source="degraded-defaults",
    )


def _heuristic_score(
    event: EventEnvelope, features: FeatureSnapshot, rule_hits: list[RuleHit]
) -> tuple[float, float]:
    score = (
        0.08 * features.failed_login_count_5m
        + 0.15 * features.txn_velocity_10m
        + 0.20 * float(features.new_device_flag)
        + 0.20 * float(features.new_region_flag)
        + 0.35 * float(features.impossible_travel_flag)
        + 0.25 * float(features.password_reset_recent_flag)
        + 0.10 * features.device_reuse_score
        + 0.10 * features.session_anomaly_score
        + 0.12 * float((event.amount or 0.0) > 1500)
        + 0.10 * len(rule_hits)
    )
    return round(min(score, 1.0), 4), 0.35


def _combine_decision(
    event: EventEnvelope,
    risk_score: float,
    confidence: float,
    rule_hits: list[RuleHit],
    degraded: bool,
    settings: CommonSettings,
) -> tuple[DecisionOutcome, list[str]]:
    rationale: list[str] = []
    hard_deny = [hit for hit in rule_hits if hit.decision == DecisionOutcome.DENY]
    review_hits = [hit for hit in rule_hits if hit.decision == DecisionOutcome.MANUAL_REVIEW]
    challenge_hits = [hit for hit in rule_hits if hit.decision == DecisionOutcome.CHALLENGE]
    if hard_deny:
        rationale.append(f"Hard deny rules triggered: {', '.join(hit.name for hit in hard_deny)}")
        return DecisionOutcome.DENY, rationale
    if review_hits:
        rationale.append(
            f"Manual review rules triggered: {', '.join(hit.name for hit in review_hits)}"
        )
        return DecisionOutcome.MANUAL_REVIEW, rationale
    if risk_score >= settings.decision_deny_threshold and confidence >= 0.65:
        rationale.append(f"Model risk score {risk_score:.2f} exceeded deny threshold.")
        return DecisionOutcome.DENY, rationale
    if challenge_hits:
        rationale.append(
            f"Challenge rules triggered: {', '.join(hit.name for hit in challenge_hits)}"
        )
        return DecisionOutcome.CHALLENGE, rationale
    if risk_score >= settings.decision_challenge_threshold:
        rationale.append(f"Model risk score {risk_score:.2f} exceeded challenge threshold.")
        return DecisionOutcome.CHALLENGE, rationale
    if degraded and event.event_type in {EventType.LOGIN_ATTEMPT, EventType.TRANSACTION_INITIATED}:
        rationale.append("Dependency degraded mode active; applying conservative challenge policy.")
        return DecisionOutcome.CHALLENGE, rationale
    rationale.append("No deny or challenge conditions met.")
    return DecisionOutcome.ALLOW, rationale


async def persist_decision(
    session: AsyncSession,
    state: AppState,
    decision: DecisionResponse,
    event_type: str,
) -> None:
    session.add(
        DecisionRecord(
            decision_id=str(decision.decision_id),
            event_id=str(decision.event_id),
            account_id=decision.account_id,
            event_type=event_type,
            outcome=decision.outcome,
            risk_score=decision.risk_score,
            confidence=decision.confidence,
            degraded_mode=decision.degraded_mode,
            decided_at=decision.decided_at,
            payload=decision.model_dump(mode="json"),
        ),
    )
    await session.commit()
    await state.producer.send(
        state.settings.decisions_topic,
        decision.model_dump(mode="json"),
        key=decision.account_id,
    )


async def fetch_existing_decision(
    session: AsyncSession,
    event_id: str,
) -> DecisionResponse | None:
    row = await session.scalar(select(DecisionRecord).where(DecisionRecord.event_id == event_id))
    if row is None:
        return None
    return DecisionResponse.model_validate(row.payload)


async def score_event(state: AppState, event: EventEnvelope) -> DecisionResponse:
    with tracer.start_as_current_span("decision_service.score") as span:
        span.set_attribute("app.event_id", str(event.event_id))
        span.set_attribute("app.account_id", event.account_id)
        span.set_attribute("app.event_type", event.event_type)
        settings = state.settings
        degraded = False
        feature_lookup_succeeded = False
        dependency_status = DependencyStatus()
        feature_response = _empty_features()
        rule_hits: list[RuleHit] = []
        risk_score = 0.0
        confidence = 0.0
        active_model_name: str | None = None
        candidate_model_name: str | None = None
        shadow_divergence = False
        contributions: list[ModelContribution] = []
        metadata: dict[str, object] = {
            "feature_source": feature_response.source,
            "feature_cache_hit": feature_response.cache_hit,
            "shadow_enabled": False,
        }

        try:
            feature_response = await state.feature_client.lookup(event)
            feature_lookup_succeeded = True
            metadata["feature_source"] = feature_response.source
            metadata["feature_cache_hit"] = feature_response.cache_hit
        except Exception as exc:
            dependency_status.feature_service = exc.__class__.__name__
            degraded = True
            metadata["scoring_mode"] = "heuristic_fallback"
            metadata["fallback_reason"] = "feature_service_unavailable"
            logger.warning("feature_lookup_failed", event_id=str(event.event_id), error=str(exc))

        if feature_lookup_succeeded:
            rules_result, model_result = await asyncio.gather(
                state.rule_client.evaluate(event, feature_response),
                state.model_client.score(event, feature_response),
                return_exceptions=True,
            )
            if isinstance(rules_result, Exception):
                dependency_status.rule_engine = rules_result.__class__.__name__
                degraded = True
                logger.warning(
                    "rule_engine_failed", event_id=str(event.event_id), error=str(rules_result)
                )
            else:
                rule_hits = rules_result.hits

            if isinstance(model_result, Exception):
                dependency_status.model_service = model_result.__class__.__name__
                degraded = True
                metadata["scoring_mode"] = "heuristic_fallback"
                metadata["fallback_reason"] = "model_service_unavailable"
                risk_score, confidence = _heuristic_score(
                    event, feature_response.snapshot, rule_hits
                )
                logger.warning(
                    "model_service_failed", event_id=str(event.event_id), error=str(model_result)
                )
            else:
                risk_score = model_result.risk_score
                confidence = model_result.confidence
                active_model_name = model_result.model_name
                candidate_model_name = model_result.candidate_model_name
                shadow_divergence = model_result.divergence
                contributions = model_result.contributions
                metadata["scoring_mode"] = "ml_inference"
                metadata["model_version"] = model_result.model_version
                metadata["candidate_risk_score"] = model_result.candidate_risk_score
                metadata["candidate_confidence"] = model_result.candidate_confidence
                metadata["shadow_enabled"] = model_result.shadow_enabled
        else:
            dependency_status.rule_engine = "skipped_missing_features"
            dependency_status.model_service = "skipped_missing_features"
            risk_score, confidence = _heuristic_score(event, feature_response.snapshot, rule_hits)
            logger.warning("feature_degraded_scoring", event_id=str(event.event_id))

        metadata["feature_computed_at"] = feature_response.computed_at.isoformat()
        metadata["rule_hit_count"] = len(rule_hits)

        outcome, rationale = _combine_decision(
            event,
            risk_score,
            confidence,
            rule_hits,
            degraded,
            settings,
        )
        if shadow_divergence:
            rationale.append("Active and shadow models diverged on this event.")

        response = DecisionResponse(
            event_id=event.event_id,
            account_id=event.account_id,
            outcome=outcome,
            risk_score=round(risk_score, 4),
            confidence=round(confidence, 4),
            rationale=rationale,
            rule_hits=rule_hits,
            feature_snapshot=feature_response.snapshot,
            active_model_name=active_model_name,
            candidate_model_name=candidate_model_name,
            shadow_divergence=shadow_divergence,
            degraded_mode=degraded,
            dependency_status=dependency_status,
            contributions=contributions,
            decided_at=datetime.now(tz=UTC),
            metadata=metadata,
        )
        span.set_attribute("app.outcome", response.outcome)
        span.set_attribute("app.degraded_mode", response.degraded_mode)
        span.set_attribute("app.rule_hits.count", len(response.rule_hits))
        decision_outcomes_total.labels(response.outcome, str(response.degraded_mode).lower()).inc()
        return response


async def consume_forever(app) -> None:
    state: AppState = app.state.container
    await state.consumer.start()
    try:
        async for message in state.consumer:
            consumer_context = extract_trace_context(message.headers)
            with tracer.start_as_current_span(
                "decision_service.consume_raw_event",
                context=consumer_context,
                kind=SpanKind.CONSUMER,
            ) as span:
                span.set_attribute("messaging.destination.name", message.topic)
                span.set_attribute("messaging.kafka.partition", message.partition)
                span.set_attribute("messaging.kafka.offset", message.offset)
                try:
                    event = EventEnvelope.model_validate(message.value)
                    bind_log_context(
                        kafka_topic=message.topic,
                        kafka_partition=message.partition,
                        kafka_offset=message.offset,
                        event_id=str(event.event_id),
                        account_id=event.account_id,
                    )
                    if not event.is_decision_candidate:
                        continue
                    async with state.session_factory() as session:
                        existing = await fetch_existing_decision(session, str(event.event_id))
                        if existing is not None:
                            logger.info("decision_consumer_replay_skipped")
                            continue
                    decision = await score_event(state, event)
                    async with state.session_factory() as session:
                        await persist_decision(session, state, decision, event.event_type)
                    kafka_consumer_lag.labels(state.settings.service_name, message.topic).set(0)
                except Exception as exc:
                    await state.producer.publish_dead_letter(
                        state.settings.dlq_topic,
                        state.settings.service_name,
                        reason=str(exc),
                        raw_payload=json.dumps(message.value),
                    )
                    dead_letter_events_total.labels(
                        state.settings.service_name, exc.__class__.__name__
                    ).inc()
                    logger.exception("decision_consumer_failed", error=str(exc))
                finally:
                    clear_log_context()
                    bind_log_context(service=state.settings.service_name)
    finally:
        await state.consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = AppState(get_common_settings())
    app.state.container = state
    async with state.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await state.producer.start()
    state.consumer_task = asyncio.create_task(consume_forever(app))
    yield
    if state.consumer_task:
        state.consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.consumer_task
    await state.feature_client.close()
    await state.rule_client.close()
    await state.model_client.close()
    await state.producer.stop()
    await state.engine.dispose()


app = build_app(get_common_settings())
app.router.lifespan_context = lifespan
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


def get_state(request: Request) -> AppState:
    return request.app.state.container


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    state = get_state(request)
    async with state.session_factory() as session:
        yield session


@app.post("/v1/decisions/score", response_model=DecisionResponse)
@limiter.limit("60/minute")
async def score(payload: DecisionRequest, request: Request) -> DecisionResponse:
    if not payload.event.is_decision_candidate:
        raise HTTPException(status_code=400, detail="Event type is not eligible for decisioning")
    state = get_state(request)
    async with state.session_factory() as session:
        existing = await fetch_existing_decision(session, str(payload.event.event_id))
        if existing is not None:
            return existing
    start = perf_counter()
    response = await score_event(state, payload.event)
    async with state.session_factory() as session:
        await persist_decision(session, state, response, payload.event.event_type)
    decision_latency.labels("degraded" if response.degraded_mode else "normal").observe(
        perf_counter() - start,
    )
    return response


@app.get("/v1/decisions", response_model=list[DecisionRecordSummary])
async def list_decisions(
    account_id: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> list[DecisionRecordSummary]:
    stmt = select(DecisionRecord).order_by(desc(DecisionRecord.decided_at)).limit(min(limit, 200))
    if account_id:
        stmt = stmt.where(DecisionRecord.account_id == account_id)
    rows = (await session.scalars(stmt)).all()
    return [
        DecisionRecordSummary(
            decision_id=row.decision_id,
            event_id=row.event_id,
            account_id=row.account_id,
            event_type=row.event_type,
            outcome=row.outcome,
            risk_score=row.risk_score,
            confidence=row.confidence,
            degraded_mode=row.degraded_mode,
            decided_at=row.decided_at,
        )
        for row in rows
    ]


@app.get("/v1/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> DecisionResponse:
    row = await session.get(DecisionRecord, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return DecisionResponse.model_validate(row.payload)
