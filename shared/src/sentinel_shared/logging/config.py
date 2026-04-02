from __future__ import annotations

import ipaddress
import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace

SENSITIVE_KEYS = {
    "authorization",
    "password",
    "secret",
    "token",
    "ip_address",
    "ip",
    "ssn",
    "email",
}


def bind_log_context(**values: Any) -> None:
    sanitized = {key: sanitize(value, key) for key, value in values.items() if value is not None}
    if sanitized:
        structlog.contextvars.bind_contextvars(**sanitized)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()


def get_log_context() -> dict[str, Any]:
    return structlog.contextvars.get_contextvars()


def get_request_id() -> str | None:
    request_id = get_log_context().get("request_id")
    return str(request_id) if request_id is not None else None


def _mask_ip(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return value
    if parsed.version == 4:
        octets = value.split(".")
        return ".".join(octets[:3] + ["0"])
    return f"{parsed.exploded[:16]}::"


def sanitize(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {nested_key: sanitize(nested_value, nested_key) for nested_key, nested_value in value.items()}
    if isinstance(value, list):
        return [sanitize(item, key) for item in value]
    if isinstance(value, str) and key and key.lower() in SENSITIVE_KEYS:
        if "ip" in key.lower():
            return _mask_ip(value)
        return "***masked***"
    return value


def pii_sanitizer(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    _ = logger, method_name
    return sanitize(event_dict)


def trace_context_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    _ = logger, method_name
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


def rename_event_key(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    _ = logger, method_name
    if "event" in event_dict and "message" not in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def configure_logging(service_name: str, level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
            trace_context_processor,
            timestamper,
            pii_sanitizer,
            rename_event_key,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    clear_log_context()
    bind_log_context(service=service_name)


def get_logger(name: str | None = None) -> structlog.types.WrappedLogger:
    return structlog.get_logger(name)
