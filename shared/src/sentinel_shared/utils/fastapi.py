from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware

from sentinel_shared.config import CommonSettings
from sentinel_shared.logging import (
    bind_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
)
from sentinel_shared.telemetry import (
    active_http_requests,
    instrument_app,
    mount_metrics,
    request_counter,
    request_latency,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, settings: CommonSettings) -> None:
        super().__init__(app)
        self._settings = settings
        self._logger = get_logger(f"{settings.service_name}.http")

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        start = perf_counter()
        client_ip = request.client.host if request.client else None
        active_http_requests.labels(self._settings.service_name).inc()
        bind_log_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
        )
        try:
            response = await call_next(request)
        except Exception:
            self._logger.exception("http_request_failed")
            clear_log_context()
            bind_log_context(service=self._settings.service_name)
            raise
        finally:
            active_http_requests.labels(self._settings.service_name).dec()
        elapsed = perf_counter() - start
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            bind_log_context(
                trace_id=format(span_context.trace_id, "032x"),
                span_id=format(span_context.span_id, "016x"),
            )
        response.headers["X-Request-ID"] = request_id
        request_counter.labels(
            self._settings.service_name,
            request.method,
            request.url.path,
            response.status_code,
        ).inc()
        request_latency.labels(self._settings.service_name, request.url.path).observe(elapsed)
        self._logger.info(
            "http_request_completed",
            status_code=response.status_code,
            latency_ms=round(elapsed * 1000, 2),
            user_agent=request.headers.get("user-agent"),
        )
        clear_log_context()
        bind_log_context(service=self._settings.service_name)
        return response


def create_health_router(service_name: str) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    @router.get("/health/ready")
    async def readiness() -> dict[str, str]:
        return {"status": "ready", "service": service_name}

    return router


def build_app(settings: CommonSettings) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level)
    logger = get_logger(settings.service_name)
    app = FastAPI(title=settings.service_name, version="0.1.0")
    app.add_middleware(ObservabilityMiddleware, settings=settings)
    mount_metrics(app)
    instrument_app(app, settings)
    app.include_router(create_health_router(settings.service_name))

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception", error=str(exc), exception_type=exc.__class__.__name__
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_server_error", "service": settings.service_name},
        )

    return app
