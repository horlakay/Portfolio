from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(StrEnum):
    LOGIN_ATTEMPT = "login_attempt"
    PASSWORD_RESET = "password_reset"
    DEVICE_REGISTERED = "device_registered"
    TRANSACTION_INITIATED = "transaction_initiated"
    TRANSACTION_COMPLETED = "transaction_completed"
    TRANSACTION_FAILED = "transaction_failed"


class LoginOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CHALLENGE = "challenge"


class GeoLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str
    country: str
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    auth_result: LoginOutcome | None = None
    device_trust_level: str | None = None
    mfa_present: bool | None = None
    payment_rail: str | None = None
    merchant_id: str | None = None
    reason: str | None = None
    correlated_event_id: UUID | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str | None = None
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    user_id: str
    account_id: str
    session_id: str | None = None
    device_id: str | None = None
    ip_address: str | None = None
    geolocation: GeoLocation | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def is_decision_candidate(self) -> bool:
        return self.event_type in {
            EventType.LOGIN_ATTEMPT,
            EventType.PASSWORD_RESET,
            EventType.TRANSACTION_INITIATED,
        }


class EventIngestResponse(BaseModel):
    accepted: bool
    event_id: UUID
    idempotent_replay: bool = False
    topic: str
    trace_id: str | None = None
    stored_at: datetime
