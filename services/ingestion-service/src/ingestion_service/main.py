from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import bind_log_context, get_logger
from sentinel_shared.schemas.events import EventEnvelope, EventIngestResponse
from sentinel_shared.telemetry import events_ingested_total, get_tracer
from sentinel_shared.utils.database import create_async_engine_and_session
from sentinel_shared.utils.fastapi import build_app
from sentinel_shared.utils.kafka import JsonProducer

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
tracer = get_tracer(__name__)


class Base(DeclarativeBase):
    pass


class IngestedEvent(Base):
    __tablename__ = "ingestion_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(128))
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class AppState:
    def __init__(self, settings: CommonSettings) -> None:
        self.settings = settings
        self.engine, self.session_factory = create_async_engine_and_session(settings.database_url)
        self.producer = JsonProducer(settings.kafka_bootstrap_servers, service_name=settings.service_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_common_settings()
    state = AppState(settings)
    app.state.container = state
    async with state.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await state.producer.start()
    yield
    await state.producer.stop()
    await state.engine.dispose()


app = build_app(get_common_settings())
app.router.lifespan_context = lifespan
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


def get_state(request: Request) -> AppState:
    return request.app.state.container


async def get_session(request: Request) -> AsyncSession:
    state: AppState = get_state(request)
    async with state.session_factory() as session:
        yield session


@app.post("/v1/events", response_model=EventIngestResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("120/minute")
async def ingest_event(
    event: EventEnvelope,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> EventIngestResponse:
    state = get_state(request)
    effective_key = idempotency_key or event.idempotency_key
    bind_log_context(event_id=str(event.event_id), account_id=event.account_id, event_type=event.event_type)
    with tracer.start_as_current_span("ingestion.accept_event") as span:
        span.set_attribute("app.event_id", str(event.event_id))
        span.set_attribute("app.account_id", event.account_id)
        span.set_attribute("app.event_type", event.event_type)
        if effective_key:
            existing = await session.scalar(
                select(IngestedEvent).where(IngestedEvent.idempotency_key == effective_key),
            )
            if existing is not None:
                events_ingested_total.labels(event.event_type, "idempotent_replay").inc()
                logger.info(
                    "idempotent_replay",
                    event_id=existing.event_id,
                    idempotency_key=effective_key,
                )
                span.set_attribute("app.idempotent_replay", True)
                return EventIngestResponse(
                    accepted=True,
                    event_id=existing.event_id,
                    idempotent_replay=True,
                    topic=state.settings.raw_events_topic,
                    stored_at=existing.stored_at,
                )

        stored_at = datetime.now(tz=UTC)
        payload = event.model_copy(update={"idempotency_key": effective_key}).model_dump(mode="json")
        row = IngestedEvent(
            event_id=str(event.event_id),
            idempotency_key=effective_key,
            event_type=event.event_type,
            account_id=event.account_id,
            stored_at=stored_at,
            payload=payload,
        )
        session.add(row)
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Duplicate idempotency key") from exc

        await state.producer.send(
            state.settings.raw_events_topic,
            payload,
            key=event.account_id,
        )
        events_ingested_total.labels(event.event_type, "accepted").inc()
        logger.info(
            "event_ingested",
            event_id=str(event.event_id),
            account_id=event.account_id,
            event_type=event.event_type,
            topic=state.settings.raw_events_topic,
        )
        return EventIngestResponse(
            accepted=True,
            event_id=event.event_id,
            topic=state.settings.raw_events_topic,
            stored_at=stored_at,
        )


@app.get("/v1/events/{event_id}", status_code=status.HTTP_200_OK)
async def get_ingested_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(IngestedEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return row.payload
