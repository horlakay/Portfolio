from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .decision import ModelContribution
from .events import EventEnvelope
from .features import DriftReport, FeatureSnapshot


class ModelScoreRequest(BaseModel):
    event: EventEnvelope
    features: FeatureSnapshot


class ModelScoreResponse(BaseModel):
    risk_score: float
    confidence: float
    model_name: str
    model_version: str
    shadow_enabled: bool = False
    candidate_model_name: str | None = None
    candidate_risk_score: float | None = None
    candidate_confidence: float | None = None
    divergence: bool = False
    contributions: list[ModelContribution] = Field(default_factory=list)
    evaluated_at: datetime


class ModelMetadata(BaseModel):
    name: str
    version: str
    trained_at: datetime
    algorithm: str
    feature_names: list[str]
    precision: float
    recall: float
    f1: float
    roc_auc: float
    training_rows: int
    positive_class_rate: float


class ClassificationMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    roc_auc: float
    threshold: float
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int


class ModelEvaluationReport(BaseModel):
    generated_at: datetime
    dataset_path: str
    dataset_manifest_path: str
    rows: int
    active: ClassificationMetrics
    candidate: ClassificationMetrics


class ModelRegistry(BaseModel):
    generated_at: datetime
    dataset_path: str
    active_model: ModelMetadata
    candidate_model: ModelMetadata


class ShadowModelSummary(BaseModel):
    shadow_enabled: bool
    active_model: str
    candidate_model: str | None = None
    total_scores: int
    divergence_count: int
    divergence_rate: float
    last_compared_at: datetime | None = None


class DriftResponse(BaseModel):
    active_model: str
    report: DriftReport
