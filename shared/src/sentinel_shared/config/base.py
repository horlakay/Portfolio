from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    service_name: str = Field(default="sentinel-service", alias="SERVICE_NAME")
    service_port: int = Field(default=8000, alias="SERVICE_PORT")

    postgres_user: str = Field(default="sentinel", alias="POSTGRES_USER")
    postgres_password: str = Field(default="sentinel", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="sentinelstream", alias="POSTGRES_DB")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    kafka_bootstrap_servers: str = Field(default="redpanda:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    raw_events_topic: str = Field(default="sentinel.events.raw", alias="RAW_EVENTS_TOPIC")
    decisions_topic: str = Field(default="sentinel.events.decisions", alias="DECISIONS_TOPIC")
    feedback_topic: str = Field(default="sentinel.events.feedback", alias="FEEDBACK_TOPIC")
    dlq_topic: str = Field(default="sentinel.events.dlq", alias="DLQ_TOPIC")

    feature_service_url: str = Field(
        default="http://feature-service:8002", alias="FEATURE_SERVICE_URL"
    )
    rule_engine_url: str = Field(default="http://rule-engine:8003", alias="RULE_ENGINE_URL")
    model_service_url: str = Field(default="http://model-service:8004", alias="MODEL_SERVICE_URL")
    decision_service_url: str = Field(
        default="http://decision-service:8005", alias="DECISION_SERVICE_URL"
    )
    feedback_service_url: str = Field(
        default="http://feedback-service:8006", alias="FEEDBACK_SERVICE_URL"
    )
    ingestion_service_url: str = Field(
        default="http://ingestion-service:8001", alias="INGESTION_SERVICE_URL"
    )
    analyst_console_url: str = Field(
        default="http://analyst-console:8007", alias="ANALYST_CONSOLE_URL"
    )

    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_issuer: str = Field(default="sentinelstream", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="sentinelstream-analyst", alias="JWT_AUDIENCE")
    analyst_console_password: str = Field(default="demo-password", alias="ANALYST_CONSOLE_PASSWORD")

    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4317",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )

    decision_allow_threshold: float = Field(default=0.35, alias="DECISION_ALLOW_THRESHOLD")
    decision_challenge_threshold: float = Field(default=0.70, alias="DECISION_CHALLENGE_THRESHOLD")
    decision_deny_threshold: float = Field(default=0.90, alias="DECISION_DENY_THRESHOLD")

    model_timeout_ms: int = Field(default=40, alias="MODEL_TIMEOUT_MS")
    feature_timeout_ms: int = Field(default=30, alias="FEATURE_TIMEOUT_MS")
    rule_timeout_ms: int = Field(default=20, alias="RULE_TIMEOUT_MS")
    shadow_model_enabled: bool = Field(default=True, alias="SHADOW_MODEL_ENABLED")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_common_settings() -> CommonSettings:
    return CommonSettings()
