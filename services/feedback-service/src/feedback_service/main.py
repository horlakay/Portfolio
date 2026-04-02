from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import JSON, Boolean, DateTime, Float, String, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sentinel_shared.auth import Role, TokenClaims, require_roles
from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import get_logger
from sentinel_shared.schemas.feedback import FeedbackDecisionContext, FeedbackRecord, FeedbackSubmission
from sentinel_shared.telemetry import feedback_labels_total, get_tracer
from sentinel_shared.utils.database import create_async_engine_and_session
from sentinel_shared.utils.fastapi import build_app
from sentinel_shared.utils.kafka import JsonProducer

logger = get_logger(__name__)
tracer = get_tracer(__name__)


class Base(DeclarativeBase):
    pass


class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    actor_role: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    decision_outcome: Mapped[str] = mapped_column(String(32))
    decision_risk_score: Mapped[float] = mapped_column(Float)
    degraded_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
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
        self.producer = JsonProducer(settings.kafka_bootstrap_servers, service_name=settings.service_name)


@asynccontextmanager
async def lifespan(app):
    state = AppState(get_common_settings())
    app.state.container = state
    async with state.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await state.producer.start()
    yield
    await state.producer.stop()
    await state.engine.dispose()


app = build_app(get_common_settings())
app.router.lifespan_context = lifespan


def get_state(request: Request) -> AppState:
    return request.app.state.container


async def get_session(request: Request) -> AsyncSession:
    state = get_state(request)
    async with state.session_factory() as session:
        yield session


@app.post("/v1/feedback", response_model=FeedbackRecord)
async def submit_feedback(
    payload: FeedbackSubmission,
    request: Request,
    claims: TokenClaims = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> FeedbackRecord:
    state = get_state(request)
    with tracer.start_as_current_span("feedback.submit") as span:
        span.set_attribute("app.decision_id", str(payload.decision_id))
        span.set_attribute("app.actor_id", claims.sub)
        decision = await session.get(DecisionRecord, str(payload.decision_id))
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        decision_context = FeedbackDecisionContext(
            decision_id=decision.decision_id,
            event_id=decision.event_id,
            account_id=decision.account_id,
            outcome=decision.outcome,
            risk_score=decision.risk_score,
            confidence=decision.confidence,
            degraded_mode=decision.degraded_mode,
            decided_at=decision.decided_at,
            metadata=decision.payload.get("metadata", {}),
        )
        record = FeedbackRecord(
            **payload.model_dump(),
            actor_id=claims.sub,
            actor_role=claims.role,
            decision_context=decision_context,
        )
        session.add(
            FeedbackEntry(
                feedback_id=str(record.feedback_id),
                decision_id=str(record.decision_id),
                label=record.label,
                notes=record.notes,
                actor_id=record.actor_id,
                actor_role=record.actor_role,
                account_id=decision.account_id,
                event_id=decision.event_id,
                decision_outcome=decision.outcome,
                decision_risk_score=decision.risk_score,
                degraded_mode=decision.degraded_mode,
                submitted_at=record.submitted_at,
                payload=record.model_dump(mode="json"),
            ),
        )
        await session.commit()
        await state.producer.send(state.settings.feedback_topic, record.model_dump(mode="json"))
        feedback_labels_total.labels(record.label).inc()
        logger.info(
            "feedback_submitted",
            feedback_id=str(record.feedback_id),
            decision_id=str(record.decision_id),
            actor_id=record.actor_id,
            label=record.label,
        )
        return record


@app.get("/v1/feedback/decisions/{decision_id}", response_model=list[FeedbackRecord])
async def list_feedback(
    decision_id: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> list[FeedbackRecord]:
    rows = (
        await session.scalars(
            select(FeedbackEntry)
            .where(FeedbackEntry.decision_id == decision_id)
            .order_by(desc(FeedbackEntry.submitted_at)),
        )
    ).all()
    return [FeedbackRecord.model_validate(row.payload) for row in rows]


@app.get("/v1/feedback", response_model=list[FeedbackRecord])
async def recent_feedback(
    account_id: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> list[FeedbackRecord]:
    stmt = select(FeedbackEntry).order_by(desc(FeedbackEntry.submitted_at)).limit(min(limit, 200))
    if account_id:
        stmt = stmt.where(FeedbackEntry.account_id == account_id)
    rows = (await session.scalars(stmt)).all()
    return [FeedbackRecord.model_validate(row.payload) for row in rows]
