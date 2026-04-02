from __future__ import annotations

import json
import random
import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from sentinel_shared.auth import Role, require_roles
from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import get_logger
from sentinel_shared.schemas.decision import ModelContribution
from sentinel_shared.schemas.features import DriftMetric, DriftReport
from sentinel_shared.schemas.model import (
    DriftResponse,
    ModelEvaluationReport,
    ModelMetadata,
    ModelRegistry,
    ModelScoreRequest,
    ModelScoreResponse,
    ShadowModelSummary,
)
from sentinel_shared.telemetry import (
    drift_alerts_total,
    get_tracer,
    model_score_distribution,
    shadow_model_divergence_total,
)
from sentinel_shared.utils.fastapi import build_app
from training.pipelines.common import EVAL_DIR, FEATURE_COLUMNS, MODEL_DIR, ensure_models, feature_vector

logger = get_logger(__name__)
tracer = get_tracer(__name__)


class FaultConfig(BaseModel):
    delay_ms: int = Field(default=0, ge=0, le=5000)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass
class RunningStats:
    sum: float = 0.0
    count: int = 0

    def add(self, value: float) -> None:
        self.sum += value
        self.count += 1

    @property
    def mean(self) -> float:
        return self.sum / self.count if self.count else 0.0


@dataclass
class AppState:
    settings: CommonSettings
    fault: FaultConfig = field(default_factory=FaultConfig)
    active_artifact: dict[str, Any] = field(default_factory=dict)
    candidate_artifact: dict[str, Any] = field(default_factory=dict)
    active_metadata: dict[str, Any] = field(default_factory=dict)
    candidate_metadata: dict[str, Any] = field(default_factory=dict)
    running_stats: dict[str, RunningStats] = field(
        default_factory=lambda: {column: RunningStats() for column in FEATURE_COLUMNS},
    )
    total_scores: int = 0
    divergence_count: int = 0
    last_compared_at: datetime | None = None


def _metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_payload() -> dict[str, Any]:
    return _metadata(MODEL_DIR / "model_registry.json")


def _evaluation_payload() -> dict[str, Any]:
    return _metadata(EVAL_DIR / "latest_metrics.json")


def _load_state(settings: CommonSettings) -> AppState:
    ensure_models()
    state = AppState(settings=settings)
    state.active_artifact = joblib.load(MODEL_DIR / "active" / "model.joblib")
    state.active_metadata = _metadata(MODEL_DIR / "active" / "metadata.json")
    if settings.shadow_model_enabled:
        state.candidate_artifact = joblib.load(MODEL_DIR / "candidate" / "model.joblib")
        state.candidate_metadata = _metadata(MODEL_DIR / "candidate" / "metadata.json")
    return state


def _contributions(model: Any, vector: np.ndarray) -> list[ModelContribution]:
    importances = getattr(model, "feature_importances_", np.ones(vector.shape[1]))
    weighted = [
        ModelContribution(feature_name=feature, contribution=float(score * value))
        for feature, score, value in zip(FEATURE_COLUMNS, importances, vector[0], strict=True)
    ]
    return sorted(weighted, key=lambda item: abs(item.contribution), reverse=True)[:5]


def _psi(training_mean: float, live_mean: float) -> float:
    epsilon = 1e-6
    safe_training = max(abs(training_mean), epsilon)
    safe_live = max(abs(live_mean), epsilon)
    return float((safe_live - safe_training) * np.log(safe_live / safe_training))


def _confidence(score: float) -> float:
    return round(min(abs(score - 0.5) * 2, 1.0), 4)


@asynccontextmanager
async def lifespan(app):
    app.state.container = _load_state(get_common_settings())
    yield


app = build_app(get_common_settings())
app.router.lifespan_context = lifespan


def get_state(request: Request) -> AppState:
    return request.app.state.container


@app.post("/v1/model/score", response_model=ModelScoreResponse)
async def score_event(payload: ModelScoreRequest, request: Request) -> ModelScoreResponse:
    state = get_state(request)
    with tracer.start_as_current_span("model_service.score") as span:
        span.set_attribute("app.event_id", str(payload.event.event_id))
        span.set_attribute("app.account_id", payload.event.account_id)
        if state.fault.delay_ms:
            import asyncio

            await asyncio.sleep(state.fault.delay_ms / 1000)
        if state.fault.error_rate and random.random() < state.fault.error_rate:
            raise HTTPException(status_code=503, detail="Injected model failure")

        vector = np.array(feature_vector(payload.event, payload.features), dtype=float).reshape(1, -1)
        vector_frame = pd.DataFrame(vector, columns=FEATURE_COLUMNS)
        active_model = state.active_artifact["model"]
        risk_score = float(active_model.predict_proba(vector_frame)[0][1])
        confidence = _confidence(risk_score)
        candidate_score: float | None = None
        candidate_confidence: float | None = None
        divergence = False
        contributions = _contributions(active_model, vector)
        state.total_scores += 1

        for feature_name, value in zip(FEATURE_COLUMNS, vector[0], strict=True):
            state.running_stats[feature_name].add(float(value))
        model_score_distribution.labels(state.active_metadata["name"]).observe(risk_score)
        if state.settings.shadow_model_enabled and state.candidate_artifact:
            candidate_model = state.candidate_artifact["model"]
            candidate_score = float(candidate_model.predict_proba(vector_frame)[0][1])
            candidate_confidence = _confidence(candidate_score)
            divergence = abs(risk_score - candidate_score) >= 0.15 or (
                (risk_score >= 0.7) != (candidate_score >= 0.7)
            )
            state.last_compared_at = datetime.now(tz=UTC)
            model_score_distribution.labels(state.candidate_metadata["name"]).observe(candidate_score)
            if divergence:
                state.divergence_count += 1
                shadow_model_divergence_total.labels(
                    state.active_metadata["name"],
                    state.candidate_metadata["name"],
                ).inc()
        span.set_attribute("app.risk_score", round(risk_score, 4))
        span.set_attribute("app.shadow_divergence", divergence)
        span.set_attribute(
            "app.shadow_enabled",
            state.settings.shadow_model_enabled and bool(state.candidate_artifact),
        )
        return ModelScoreResponse(
            risk_score=round(risk_score, 4),
            confidence=confidence,
            model_name=state.active_metadata["name"],
            model_version=state.active_metadata["version"],
            shadow_enabled=state.settings.shadow_model_enabled and bool(state.candidate_artifact),
            candidate_model_name=state.candidate_metadata.get("name"),
            candidate_risk_score=round(candidate_score, 4) if candidate_score is not None else None,
            candidate_confidence=candidate_confidence,
            divergence=divergence,
            contributions=contributions,
            evaluated_at=datetime.now(tz=UTC),
        )


@app.get("/v1/model/metadata", response_model=list[ModelMetadata])
async def model_metadata(
    request: Request,
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> list[ModelMetadata]:
    state = get_state(request)
    models = [ModelMetadata.model_validate(state.active_metadata)]
    if state.settings.shadow_model_enabled and state.candidate_metadata:
        models.append(ModelMetadata.model_validate(state.candidate_metadata))
    return models


@app.get("/v1/model/evaluation/latest", response_model=ModelEvaluationReport)
async def latest_evaluation(
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> ModelEvaluationReport:
    return ModelEvaluationReport.model_validate(_evaluation_payload())


@app.get("/v1/model/registry", response_model=ModelRegistry)
async def model_registry(
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> ModelRegistry:
    return ModelRegistry.model_validate(_registry_payload())


@app.get("/v1/model/shadow/summary", response_model=ShadowModelSummary)
async def shadow_summary(
    request: Request,
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> ShadowModelSummary:
    state = get_state(request)
    divergence_rate = state.divergence_count / state.total_scores if state.total_scores else 0.0
    return ShadowModelSummary(
        shadow_enabled=state.settings.shadow_model_enabled and bool(state.candidate_artifact),
        active_model=state.active_metadata["name"],
        candidate_model=state.candidate_metadata.get("name"),
        total_scores=state.total_scores,
        divergence_count=state.divergence_count,
        divergence_rate=round(divergence_rate, 4),
        last_compared_at=state.last_compared_at,
    )


@app.get("/v1/model/drift", response_model=DriftResponse)
async def drift_report(
    request: Request,
    _: object = Depends(require_roles(Role.ANALYST, Role.ADMIN)),
) -> DriftResponse:
    state = get_state(request)
    baseline = state.active_artifact["baseline"]
    metrics: list[DriftMetric] = []
    for feature_name in FEATURE_COLUMNS:
        training_mean = float(baseline[feature_name]["mean"])
        live_mean = state.running_stats[feature_name].mean
        psi = _psi(training_mean, live_mean)
        alert = psi >= 0.25
        if alert:
            drift_alerts_total.labels(feature_name).inc()
        metrics.append(
            DriftMetric(
                feature_name=feature_name,
                training_mean=training_mean,
                live_mean=live_mean,
                population_stability_index=round(psi, 4),
                alert=alert,
            ),
        )
    return DriftResponse(
        active_model=state.active_metadata["name"],
        report=DriftReport(generated_at=datetime.now(tz=UTC), metrics=metrics),
    )


@app.post("/v1/admin/faults")
async def update_faults(
    fault: FaultConfig,
    request: Request,
    _: object = Depends(require_roles(Role.ADMIN)),
) -> dict:
    state = get_state(request)
    state.fault = fault
    logger.info("model_faults_updated", delay_ms=fault.delay_ms, error_rate=fault.error_rate)
    return {"updated": True, "fault": fault.model_dump()}


@app.post("/v1/admin/promote-shadow")
async def promote_shadow(
    request: Request,
    _: object = Depends(require_roles(Role.ADMIN)),
) -> dict:
    if not get_state(request).settings.shadow_model_enabled:
        raise HTTPException(status_code=400, detail="Shadow model support is disabled")
    shutil.copyfile(MODEL_DIR / "candidate" / "model.joblib", MODEL_DIR / "active" / "model.joblib")
    shutil.copyfile(MODEL_DIR / "candidate" / "metadata.json", MODEL_DIR / "active" / "metadata.json")
    app.state.container = _load_state(get_common_settings())
    registry = _registry_payload()
    registry["generated_at"] = datetime.now(tz=UTC).isoformat()
    registry["active_model"] = app.state.container.active_metadata
    if app.state.container.candidate_metadata:
        registry["candidate_model"] = app.state.container.candidate_metadata
    (MODEL_DIR / "model_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    logger.info("shadow_model_promoted")
    return {"promoted": True, "active_model": app.state.container.active_metadata["name"]}


@app.post("/v1/admin/reload")
async def reload_models(_: object = Depends(require_roles(Role.ADMIN))) -> dict:
    app.state.container = _load_state(get_common_settings())
    return {
        "reloaded": True,
        "active_model": app.state.container.active_metadata["name"],
        "shadow_enabled": app.state.container.settings.shadow_model_enabled,
    }
