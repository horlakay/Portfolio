from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed_login_count_5m: int = 0
    successful_login_count_24h: int = 0
    distinct_devices_7d: int = 0
    distinct_ips_24h: int = 0
    avg_txn_amount_30d: float = 0.0
    txn_velocity_10m: int = 0
    new_device_flag: bool = False
    new_region_flag: bool = False
    impossible_travel_flag: bool = False
    password_reset_recent_flag: bool = False
    high_risk_hour_flag: bool = False
    account_age_days: int = 0
    device_reuse_score: float = 0.0
    baseline_amount_deviation: float = 0.0
    session_anomaly_score: float = 0.0


class FeatureLookupResponse(BaseModel):
    snapshot: FeatureSnapshot
    computed_at: datetime
    cache_hit: bool = False
    source: str = "postgres"


class DriftMetric(BaseModel):
    feature_name: str
    training_mean: float
    live_mean: float
    population_stability_index: float
    alert: bool = False


class DriftReport(BaseModel):
    generated_at: datetime
    metrics: list[DriftMetric]
