from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from aiokafka import AIOKafkaConsumer
from fastapi import Depends, FastAPI, HTTPException, Request
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sentinel_shared.auth import Role, require_roles
from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import bind_log_context, clear_log_context, get_logger
from sentinel_shared.schemas.events import EventEnvelope, EventType, LoginOutcome
from sentinel_shared.schemas.features import FeatureLookupResponse, FeatureSnapshot
from sentinel_shared.telemetry import (
    dead_letter_events_total,
    extract_trace_context,
    feature_cache_operations_total,
    feature_lookup_latency_seconds,
    get_tracer,
    kafka_consumer_lag,
)
from sentinel_shared.utils.database import create_async_engine_and_session
from sentinel_shared.utils.fastapi import build_app
from sentinel_shared.utils.geo import is_impossible_travel
from sentinel_shared.utils.kafka import JsonProducer
from sqlalchemy import JSON, DateTime, Float, Integer, String, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = get_logger(__name__)
tracer = get_tracer(__name__)


class Base(DeclarativeBase):
    pass


class FeatureEvent(Base):
    __tablename__ = "feature_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(128))
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    auth_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)


class AccountProfile(Base):
    __tablename__ = "feature_account_profiles"

    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    known_devices: Mapped[list[str]] = mapped_column(JSON, default=list)
    known_regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    avg_txn_amount_30d: Mapped[float] = mapped_column(Float, default=0.0)
    txn_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    last_password_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_successful_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_login_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class FaultConfig(BaseModel):
    delay_ms: int = Field(default=0, ge=0, le=5000)
    cache_enabled: bool = True


@dataclass
class AppState:
    settings: CommonSettings
    engine: Any
    session_factory: Any
    redis: Redis
    producer: JsonProducer
    consumer: AIOKafkaConsumer
    fault: FaultConfig
    consumer_task: asyncio.Task | None = None


async def get_or_create_profile(session: AsyncSession, event: EventEnvelope) -> AccountProfile:
    profile = await session.get(AccountProfile, event.account_id)
    if profile is None:
        profile = AccountProfile(
            account_id=event.account_id,
            user_id=event.user_id,
            first_seen_at=event.timestamp,
            last_updated_at=event.timestamp,
            known_devices=[],
            known_regions=[],
        )
        session.add(profile)
        await session.flush()
    return profile


def _append_unique(values: list[str], candidate: str | None) -> list[str]:
    if candidate and candidate not in values:
        return [*values, candidate]
    return values


async def process_event(session: AsyncSession, state: AppState, event: EventEnvelope) -> None:
    with tracer.start_as_current_span(
        "feature_service.process_event", kind=SpanKind.CONSUMER
    ) as span:
        span.set_attribute("app.event_id", str(event.event_id))
        span.set_attribute("app.account_id", event.account_id)
        existing = await session.get(FeatureEvent, str(event.event_id))
        if existing is not None:
            return

        profile = await get_or_create_profile(session, event)
        profile.last_updated_at = event.timestamp
        profile.known_devices = _append_unique(profile.known_devices or [], event.device_id)
        profile.known_regions = _append_unique(
            profile.known_regions or [],
            event.geolocation.region if event.geolocation else None,
        )

        if event.event_type == EventType.PASSWORD_RESET:
            profile.last_password_reset_at = event.timestamp

        if (
            event.event_type == EventType.LOGIN_ATTEMPT
            and event.metadata.auth_result == LoginOutcome.SUCCESS
        ):
            profile.last_successful_login_at = event.timestamp
            if event.geolocation:
                profile.last_login_latitude = event.geolocation.latitude
                profile.last_login_longitude = event.geolocation.longitude

        if event.amount is not None and event.event_type in {
            EventType.TRANSACTION_INITIATED,
            EventType.TRANSACTION_COMPLETED,
        }:
            current_count = profile.txn_count_30d or 0
            current_avg = profile.avg_txn_amount_30d or 0.0
            updated_count = current_count + 1
            profile.avg_txn_amount_30d = (
                (current_avg * current_count) + event.amount
            ) / updated_count
            profile.txn_count_30d = updated_count

        session.add(
            FeatureEvent(
                event_id=str(event.event_id),
                event_type=event.event_type,
                user_id=event.user_id,
                account_id=event.account_id,
                session_id=event.session_id,
                device_id=event.device_id,
                ip_address=event.ip_address,
                region=event.geolocation.region if event.geolocation else None,
                country=event.geolocation.country if event.geolocation else None,
                latitude=event.geolocation.latitude if event.geolocation else None,
                longitude=event.geolocation.longitude if event.geolocation else None,
                amount=event.amount,
                currency=event.currency,
                auth_result=event.metadata.auth_result,
                occurred_at=event.timestamp,
                raw_payload=event.model_dump(mode="json"),
            ),
        )
        await session.commit()
        try:
            await state.redis.delete(f"feature-base:{event.account_id}")
            feature_cache_operations_total.labels("delete", "success").inc()
        except Exception as exc:
            feature_cache_operations_total.labels("delete", "error").inc()
            logger.warning(
                "feature_cache_invalidation_failed", error=str(exc), account_id=event.account_id
            )


def _history_filters(event: EventEnvelope, start: datetime | None = None) -> list:
    filters = [
        FeatureEvent.account_id == event.account_id,
        FeatureEvent.event_id != str(event.event_id),
        FeatureEvent.occurred_at <= event.timestamp,
    ]
    if start is not None:
        filters.append(FeatureEvent.occurred_at >= start)
    return filters


async def _history_distinct_values(
    session: AsyncSession,
    column,
    filters: list,
) -> list[str]:
    values = (
        await session.scalars(
            select(distinct(column)).where(*filters, column.is_not(None)),
        )
    ).all()
    return [value for value in values if value]


async def _previous_successful_login(
    session: AsyncSession,
    event: EventEnvelope,
) -> FeatureEvent | None:
    return await session.scalar(
        select(FeatureEvent)
        .where(
            *_history_filters(event),
            FeatureEvent.event_type == EventType.LOGIN_ATTEMPT,
            FeatureEvent.auth_result == LoginOutcome.SUCCESS,
        )
        .order_by(desc(FeatureEvent.occurred_at))
        .limit(1),
    )


def derive_feature_snapshot(base: dict[str, Any], event: EventEnvelope) -> FeatureSnapshot:
    impossible_travel = is_impossible_travel(
        float(base["last_login_latitude"]) if base.get("last_login_latitude") is not None else None,
        float(base["last_login_longitude"])
        if base.get("last_login_longitude") is not None
        else None,
        datetime.fromisoformat(base["last_successful_login_at"])
        if base.get("last_successful_login_at")
        else None,
        event.geolocation.latitude if event.geolocation else None,
        event.geolocation.longitude if event.geolocation else None,
        event.timestamp,
    )
    avg_txn_amount = float(base.get("avg_txn_amount_30d", 0.0))
    amount_deviation = (
        abs((event.amount or 0.0) - avg_txn_amount) / max(avg_txn_amount, 1.0)
        if event.amount is not None
        else 0.0
    )
    new_device_flag = bool(event.device_id and event.device_id not in base.get("known_devices", []))
    new_region_flag = bool(
        event.geolocation and event.geolocation.region not in base.get("known_regions", [])
    )
    high_risk_hour_flag = event.timestamp.hour in {0, 1, 2, 3, 4, 5}
    session_anomaly_score = round(
        (0.35 if new_device_flag else 0.0)
        + (0.35 if new_region_flag else 0.0)
        + (0.60 if impossible_travel else 0.0)
        + (0.15 if high_risk_hour_flag else 0.0)
        + (0.10 if float(base.get("device_reuse_score", 0.0)) >= 2 else 0.0),
        3,
    )
    return FeatureSnapshot(
        failed_login_count_5m=int(base.get("failed_login_count_5m", 0)),
        successful_login_count_24h=int(base.get("successful_login_count_24h", 0)),
        distinct_devices_7d=int(base.get("distinct_devices_7d", 0)),
        distinct_ips_24h=int(base.get("distinct_ips_24h", 0)),
        avg_txn_amount_30d=avg_txn_amount,
        txn_velocity_10m=int(base.get("txn_velocity_10m", 0)),
        new_device_flag=new_device_flag,
        new_region_flag=new_region_flag,
        impossible_travel_flag=impossible_travel,
        password_reset_recent_flag=bool(base.get("password_reset_recent_flag", False)),
        high_risk_hour_flag=high_risk_hour_flag,
        account_age_days=int(base.get("account_age_days", 0)),
        device_reuse_score=float(base.get("device_reuse_score", 0.0)),
        baseline_amount_deviation=round(amount_deviation, 4),
        session_anomaly_score=session_anomaly_score,
    )


async def build_feature_snapshot(
    session: AsyncSession,
    state: AppState,
    event: EventEnvelope,
) -> FeatureLookupResponse:
    with tracer.start_as_current_span("feature_service.build_snapshot") as span:
        span.set_attribute("app.event_id", str(event.event_id))
        span.set_attribute("app.account_id", event.account_id)
        base_cache_key = f"feature-base:{event.account_id}"
        now = event.timestamp
        profile = await session.get(AccountProfile, event.account_id)
        historical_devices: list[str] = []
        historical_regions: list[str] = []
        prior_login: FeatureEvent | None = None
        cache_hit = False
        current_event_already_indexed = (
            await session.get(FeatureEvent, str(event.event_id)) is not None
        )

        base: dict[str, Any] = {}
        if state.fault.cache_enabled and not current_event_already_indexed:
            try:
                cached_payload = await state.redis.get(base_cache_key)
                if cached_payload:
                    cache_hit = True
                    base = json.loads(cached_payload)
                    feature_cache_operations_total.labels("get", "hit").inc()
                else:
                    feature_cache_operations_total.labels("get", "miss").inc()
            except Exception as exc:
                feature_cache_operations_total.labels("get", "error").inc()
                logger.warning(
                    "feature_cache_get_failed", error=str(exc), account_id=event.account_id
                )
        else:
            feature_cache_operations_total.labels("get", "disabled").inc()

        if not base:
            windows = {
                "failed_login_count_5m": now - timedelta(minutes=5),
                "successful_login_count_24h": now - timedelta(hours=24),
                "distinct_devices_7d": now - timedelta(days=7),
                "distinct_ips_24h": now - timedelta(hours=24),
                "txn_velocity_10m": now - timedelta(minutes=10),
                "password_reset_recent_flag": now - timedelta(minutes=30),
            }
            failed_login_count_5m = await session.scalar(
                select(func.count())
                .select_from(FeatureEvent)
                .where(
                    *_history_filters(event, windows["failed_login_count_5m"]),
                    FeatureEvent.event_type == EventType.LOGIN_ATTEMPT,
                    FeatureEvent.auth_result == LoginOutcome.FAILURE,
                ),
            )
            successful_login_count_24h = await session.scalar(
                select(func.count())
                .select_from(FeatureEvent)
                .where(
                    *_history_filters(event, windows["successful_login_count_24h"]),
                    FeatureEvent.event_type == EventType.LOGIN_ATTEMPT,
                    FeatureEvent.auth_result == LoginOutcome.SUCCESS,
                ),
            )
            distinct_devices_7d = await session.scalar(
                select(func.count(distinct(FeatureEvent.device_id))).where(
                    *_history_filters(event, windows["distinct_devices_7d"]),
                ),
            )
            distinct_ips_24h = await session.scalar(
                select(func.count(distinct(FeatureEvent.ip_address))).where(
                    *_history_filters(event, windows["distinct_ips_24h"]),
                ),
            )
            avg_txn_amount_30d = await session.scalar(
                select(func.avg(FeatureEvent.amount)).where(
                    *_history_filters(event, now - timedelta(days=30)),
                    FeatureEvent.event_type.in_(
                        [EventType.TRANSACTION_INITIATED, EventType.TRANSACTION_COMPLETED],
                    ),
                ),
            )
            txn_velocity_10m = await session.scalar(
                select(func.count())
                .select_from(FeatureEvent)
                .where(
                    *_history_filters(event, windows["txn_velocity_10m"]),
                    FeatureEvent.event_type.in_(
                        [EventType.TRANSACTION_INITIATED, EventType.TRANSACTION_COMPLETED],
                    ),
                ),
            )
            password_reset_recent_count = await session.scalar(
                select(func.count())
                .select_from(FeatureEvent)
                .where(
                    *_history_filters(event, windows["password_reset_recent_flag"]),
                    FeatureEvent.event_type == EventType.PASSWORD_RESET,
                ),
            )
            device_reuse_accounts = 0
            if event.device_id:
                reuse_count = await session.scalar(
                    select(func.count(distinct(FeatureEvent.account_id))).where(
                        FeatureEvent.device_id == event.device_id,
                        FeatureEvent.event_id != str(event.event_id),
                        FeatureEvent.occurred_at >= now - timedelta(hours=24),
                        FeatureEvent.occurred_at <= now,
                    ),
                )
                device_reuse_accounts = reuse_count or 0
            historical_devices = await _history_distinct_values(
                session,
                FeatureEvent.device_id,
                _history_filters(event),
            )
            historical_regions = await _history_distinct_values(
                session,
                FeatureEvent.region,
                _history_filters(event),
            )
            prior_login = await _previous_successful_login(session, event)
            base = {
                "failed_login_count_5m": failed_login_count_5m or 0,
                "successful_login_count_24h": successful_login_count_24h or 0,
                "distinct_devices_7d": distinct_devices_7d or 0,
                "distinct_ips_24h": distinct_ips_24h or 0,
                "avg_txn_amount_30d": float(avg_txn_amount_30d or 0.0),
                "txn_velocity_10m": txn_velocity_10m or 0,
                "password_reset_recent_flag": bool(password_reset_recent_count),
                "device_reuse_score": float(device_reuse_accounts or 0),
                "account_age_days": (
                    max((now - profile.first_seen_at).days, 0) if profile is not None else 0
                ),
                "known_devices": historical_devices,
                "known_regions": historical_regions,
                "last_successful_login_at": (
                    prior_login.occurred_at.isoformat() if prior_login is not None else None
                ),
                "last_login_latitude": prior_login.latitude if prior_login is not None else None,
                "last_login_longitude": prior_login.longitude if prior_login is not None else None,
            }
            if state.fault.cache_enabled and not current_event_already_indexed:
                try:
                    await state.redis.set(base_cache_key, json.dumps(base), ex=15)
                    feature_cache_operations_total.labels("set", "success").inc()
                except Exception as exc:
                    feature_cache_operations_total.labels("set", "error").inc()
                    logger.warning(
                        "feature_cache_set_failed", error=str(exc), account_id=event.account_id
                    )

        snapshot = derive_feature_snapshot(base, event)
        span.set_attribute("app.cache_hit", cache_hit)
        return FeatureLookupResponse(
            snapshot=snapshot,
            computed_at=datetime.now(tz=UTC),
            cache_hit=cache_hit,
            source="redis+postgres" if cache_hit else "postgres",
        )


async def consume_forever(app: FastAPI) -> None:
    state: AppState = app.state.container
    await state.consumer.start()
    logger.info("feature_consumer_started")
    try:
        async for message in state.consumer:
            consumer_context = extract_trace_context(message.headers)
            with tracer.start_as_current_span(
                "feature_service.consume_raw_event",
                context=consumer_context,
                kind=SpanKind.CONSUMER,
            ) as span:
                span.set_attribute("messaging.destination.name", message.topic)
                span.set_attribute("messaging.kafka.partition", message.partition)
                span.set_attribute("messaging.kafka.offset", message.offset)
                async with state.session_factory() as session:
                    try:
                        event = EventEnvelope.model_validate(message.value)
                        bind_log_context(
                            kafka_topic=message.topic,
                            kafka_partition=message.partition,
                            kafka_offset=message.offset,
                            event_id=str(event.event_id),
                            account_id=event.account_id,
                        )
                        await process_event(session, state, event)
                        kafka_consumer_lag.labels(state.settings.service_name, message.topic).set(0)
                    except Exception as exc:
                        raw_payload = json.dumps(message.value)
                        await state.producer.publish_dead_letter(
                            state.settings.dlq_topic,
                            state.settings.service_name,
                            reason=str(exc),
                            raw_payload=raw_payload,
                        )
                        dead_letter_events_total.labels(
                            state.settings.service_name, exc.__class__.__name__
                        ).inc()
                        logger.exception("feature_event_failed", error=str(exc))
                    finally:
                        clear_log_context()
                        bind_log_context(service=state.settings.service_name)
    finally:
        await state.consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_common_settings()
    engine, session_factory = create_async_engine_and_session(settings.database_url)
    redis = redis_from_url(settings.redis_url, decode_responses=True)
    producer = JsonProducer(settings.kafka_bootstrap_servers, service_name=settings.service_name)
    consumer = AIOKafkaConsumer(
        settings.raw_events_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="feature-service",
        auto_offset_reset="earliest",
        value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
    )
    state = AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        producer=producer,
        consumer=consumer,
        fault=FaultConfig(),
    )
    app.state.container = state
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await producer.start()
        state.consumer_task = asyncio.create_task(consume_forever(app))
        yield
    finally:
        if state.consumer_task:
            state.consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.consumer_task
        with contextlib.suppress(Exception):
            await producer.stop()
        with contextlib.suppress(Exception):
            await consumer.stop()
        with contextlib.suppress(Exception):
            await redis.aclose()
        with contextlib.suppress(Exception):
            await engine.dispose()


app = build_app(get_common_settings())
app.router.lifespan_context = lifespan


def get_state(request: Request) -> AppState:
    return request.app.state.container


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    state = get_state(request)
    async with state.session_factory() as session:
        yield session


@app.post("/v1/features/lookup", response_model=FeatureLookupResponse)
async def lookup_features(
    event: EventEnvelope,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> FeatureLookupResponse:
    state = get_state(request)
    if state.fault.delay_ms:
        await asyncio.sleep(state.fault.delay_ms / 1000)
    start = perf_counter()
    response = await build_feature_snapshot(session, state, event)
    feature_lookup_latency_seconds.labels("hit" if response.cache_hit else "miss").observe(
        perf_counter() - start,
    )
    return response


@app.get("/v1/features/accounts/{account_id}")
async def get_account_profile(
    account_id: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> dict:
    profile = await session.get(AccountProfile, account_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "account_id": profile.account_id,
        "first_seen_at": profile.first_seen_at,
        "known_devices": profile.known_devices,
        "known_regions": profile.known_regions,
        "avg_txn_amount_30d": profile.avg_txn_amount_30d,
        "txn_count_30d": profile.txn_count_30d,
    }


@app.post("/v1/admin/faults")
async def update_faults(
    fault: FaultConfig,
    request: Request,
    _: object = Depends(require_roles(Role.ADMIN)),
) -> dict:
    state = get_state(request)
    state.fault = fault
    logger.info(
        "feature_faults_updated", delay_ms=fault.delay_ms, cache_enabled=fault.cache_enabled
    )
    return {"updated": True, "fault": fault.model_dump()}
