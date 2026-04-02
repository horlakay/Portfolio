from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sentinel_shared.schemas.events import EventEnvelope, EventType
from sentinel_shared.schemas.features import FeatureSnapshot
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "synthetic"
MODEL_DIR = ROOT / "training" / "models"
EVAL_DIR = ROOT / "training" / "evaluation"
DEFAULT_DATASET_PATH = DATA_DIR / "synthetic_fraud_training.csv"
DEFAULT_MANIFEST_PATH = DATA_DIR / "synthetic_fraud_training_manifest.json"

FEATURE_COLUMNS = [
    "failed_login_count_5m",
    "successful_login_count_24h",
    "distinct_devices_7d",
    "distinct_ips_24h",
    "avg_txn_amount_30d",
    "txn_velocity_10m",
    "new_device_flag",
    "new_region_flag",
    "impossible_travel_flag",
    "password_reset_recent_flag",
    "high_risk_hour_flag",
    "account_age_days",
    "device_reuse_score",
    "baseline_amount_deviation",
    "session_anomaly_score",
    "amount",
    "event_login_attempt",
    "event_password_reset",
    "event_transaction_initiated",
]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _path_reference(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _json_contains(path: Path, required_keys: set[str]) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return required_keys.issubset(payload.keys())


def _event_one_hot(event_type: str) -> dict[str, int]:
    return {
        "event_login_attempt": int(event_type == EventType.LOGIN_ATTEMPT),
        "event_password_reset": int(event_type == EventType.PASSWORD_RESET),
        "event_transaction_initiated": int(event_type == EventType.TRANSACTION_INITIATED),
    }


def feature_vector(event: EventEnvelope, features: FeatureSnapshot) -> list[float]:
    return [
        float(features.failed_login_count_5m),
        float(features.successful_login_count_24h),
        float(features.distinct_devices_7d),
        float(features.distinct_ips_24h),
        float(features.avg_txn_amount_30d),
        float(features.txn_velocity_10m),
        float(features.new_device_flag),
        float(features.new_region_flag),
        float(features.impossible_travel_flag),
        float(features.password_reset_recent_flag),
        float(features.high_risk_hour_flag),
        float(features.account_age_days),
        float(features.device_reuse_score),
        float(features.baseline_amount_deviation),
        float(features.session_anomaly_score),
        float(event.amount or 0.0),
        *_event_one_hot(event.event_type).values(),
    ]


def generate_synthetic_dataset(rows: int = 8000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rnd = random.Random(seed)
    samples: list[dict[str, float | int | str]] = []

    for _ in range(rows):
        event_type = rnd.choices(
            [EventType.LOGIN_ATTEMPT, EventType.PASSWORD_RESET, EventType.TRANSACTION_INITIATED],
            weights=[0.45, 0.1, 0.45],
        )[0]
        failed_login_count_5m = int(rng.poisson(1.2))
        successful_login_count_24h = int(rng.poisson(2.6))
        distinct_devices_7d = max(1, int(rng.normal(1.6, 0.8)))
        distinct_ips_24h = max(1, int(rng.normal(1.5, 0.9)))
        avg_txn_amount_30d = max(0.0, float(rng.gamma(2.5, 60)))
        amount = (
            max(0.0, float(rng.gamma(2.2, 80)))
            if event_type == EventType.TRANSACTION_INITIATED
            else 0.0
        )
        txn_velocity_10m = int(rng.poisson(0.8))
        new_device_flag = rnd.random() < 0.12
        new_region_flag = rnd.random() < 0.08
        impossible_travel_flag = rnd.random() < 0.03
        password_reset_recent_flag = rnd.random() < 0.05
        high_risk_hour_flag = rnd.random() < 0.25
        account_age_days = max(0, int(rng.gamma(4.0, 45)))
        device_reuse_score = max(0.0, float(rng.gamma(1.5, 0.8)))
        baseline_amount_deviation = (
            abs(amount - avg_txn_amount_30d) / max(avg_txn_amount_30d, 1.0) if amount else 0.0
        )
        session_anomaly_score = round(
            0.30 * new_device_flag
            + 0.30 * new_region_flag
            + 0.55 * impossible_travel_flag
            + 0.10 * high_risk_hour_flag
            + 0.10 * (device_reuse_score > 2),
            4,
        )
        fraud_logit = (
            0.35 * failed_login_count_5m
            + 0.55 * new_device_flag
            + 0.45 * new_region_flag
            + 0.80 * impossible_travel_flag
            + 0.60 * password_reset_recent_flag
            + 0.25 * txn_velocity_10m
            + 0.15 * device_reuse_score
            + 0.20 * baseline_amount_deviation
            + 0.35 * session_anomaly_score
            + 0.18 * (amount > 1200)
            - 0.01 * successful_login_count_24h
            - 0.002 * min(account_age_days, 365)
        )
        probability = 1 / (1 + math.exp(-(fraud_logit - 1.8)))
        label = int(rnd.random() < probability)
        samples.append(
            {
                "event_type": event_type,
                "failed_login_count_5m": failed_login_count_5m,
                "successful_login_count_24h": successful_login_count_24h,
                "distinct_devices_7d": distinct_devices_7d,
                "distinct_ips_24h": distinct_ips_24h,
                "avg_txn_amount_30d": avg_txn_amount_30d,
                "txn_velocity_10m": txn_velocity_10m,
                "new_device_flag": int(new_device_flag),
                "new_region_flag": int(new_region_flag),
                "impossible_travel_flag": int(impossible_travel_flag),
                "password_reset_recent_flag": int(password_reset_recent_flag),
                "high_risk_hour_flag": int(high_risk_hour_flag),
                "account_age_days": account_age_days,
                "device_reuse_score": round(device_reuse_score, 4),
                "baseline_amount_deviation": round(baseline_amount_deviation, 4),
                "session_anomaly_score": session_anomaly_score,
                "amount": round(amount, 2),
                **_event_one_hot(event_type),
                "label": label,
            },
        )
    return pd.DataFrame(samples)


def write_dataset_bundle(
    dataframe: pd.DataFrame,
    *,
    seed: int,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> None:
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(dataset_path, index=False)
    _write_json(
        manifest_path,
        {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "rows": int(len(dataframe)),
            "seed": seed,
            "fraud_rate": round(float(dataframe["label"].mean()), 4),
            "feature_columns": FEATURE_COLUMNS,
            "dataset_path": _path_reference(dataset_path),
        },
    )


@dataclass
class TrainingArtifacts:
    active_model_path: Path
    candidate_model_path: Path
    evaluation_path: Path
    shadow_report_path: Path
    registry_path: Path
    dataset_path: Path
    dataset_manifest_path: Path


def _classification_metrics(
    probabilities: np.ndarray, labels: pd.Series, threshold: float
) -> dict[str, float | int]:
    predicted = (probabilities >= threshold).astype(int)
    tp = int(((predicted == 1) & (labels == 1)).sum())
    tn = int(((predicted == 0) & (labels == 0)).sum())
    fp = int(((predicted == 1) & (labels == 0)).sum())
    fn = int(((predicted == 0) & (labels == 1)).sum())
    return {
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "threshold": threshold,
        "true_positives": tp,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
    }


def _write_metadata(
    target_dir: Path,
    name: str,
    algorithm: str,
    metrics: dict[str, float | int],
    *,
    training_rows: int,
    positive_class_rate: float,
) -> dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "name": name,
        "version": datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S"),
        "trained_at": datetime.now(tz=UTC).isoformat(),
        "algorithm": algorithm,
        "feature_names": FEATURE_COLUMNS,
        "training_rows": training_rows,
        "positive_class_rate": round(positive_class_rate, 4),
        **metrics,
    }
    _write_json(target_dir / "metadata.json", metadata)
    return metadata


def _shadow_report(
    active_prob: np.ndarray,
    candidate_prob: np.ndarray,
    labels: pd.Series,
    *,
    threshold: float,
) -> dict[str, Any]:
    active_pred = active_prob >= threshold
    candidate_pred = candidate_prob >= threshold
    divergence_mask = active_pred != candidate_pred
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "threshold": threshold,
        "rows_compared": int(len(labels)),
        "divergence_count": int(divergence_mask.sum()),
        "divergence_rate": round(float(divergence_mask.mean()), 4),
        "avg_score_gap": round(float(np.abs(active_prob - candidate_prob).mean()), 4),
        "fraud_rate_eval": round(float(labels.mean()), 4),
    }


def train_models(
    dataframe: pd.DataFrame,
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    dataset_manifest_path: Path = DEFAULT_MANIFEST_PATH,
    model_dir: Path = MODEL_DIR,
    evaluation_dir: Path = EVAL_DIR,
    threshold: float = 0.5,
) -> TrainingArtifacts:
    model_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "active").mkdir(parents=True, exist_ok=True)
    (model_dir / "candidate").mkdir(parents=True, exist_ok=True)

    x = dataframe[FEATURE_COLUMNS]
    y = dataframe["label"]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.25,
        stratify=y,
        random_state=42,
    )

    active = GradientBoostingClassifier(random_state=42)
    active.fit(x_train, y_train)
    active_prob = active.predict_proba(x_test)[:, 1]
    active_metrics = _classification_metrics(active_prob, y_test, threshold)

    candidate = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        random_state=42,
        class_weight="balanced_subsample",
    )
    candidate.fit(x_train, y_train)
    candidate_prob = candidate.predict_proba(x_test)[:, 1]
    candidate_metrics = _classification_metrics(candidate_prob, y_test, threshold)

    baseline_stats: dict[str, dict[str, float]] = {}
    for column in FEATURE_COLUMNS:
        std = float(dataframe[column].std())
        baseline_stats[column] = {
            "mean": float(dataframe[column].mean()),
            "std": 1.0 if np.isnan(std) or std == 0.0 else std,
        }
    dataset_ref = _path_reference(dataset_path)
    joblib.dump(
        {
            "model": active,
            "feature_names": FEATURE_COLUMNS,
            "baseline": baseline_stats,
            "dataset_path": dataset_ref,
        },
        model_dir / "active" / "model.joblib",
    )
    joblib.dump(
        {
            "model": candidate,
            "feature_names": FEATURE_COLUMNS,
            "baseline": baseline_stats,
            "dataset_path": dataset_ref,
        },
        model_dir / "candidate" / "model.joblib",
    )
    positive_class_rate = float(dataframe["label"].mean())
    active_metadata = _write_metadata(
        model_dir / "active",
        "fraud-gbt",
        "GradientBoostingClassifier",
        active_metrics,
        training_rows=len(dataframe),
        positive_class_rate=positive_class_rate,
    )
    candidate_metadata = _write_metadata(
        model_dir / "candidate",
        "fraud-rf-shadow",
        "RandomForestClassifier",
        candidate_metrics,
        training_rows=len(dataframe),
        positive_class_rate=positive_class_rate,
    )

    evaluation = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "dataset_path": dataset_ref,
        "dataset_manifest_path": _path_reference(dataset_manifest_path),
        "rows": int(len(dataframe)),
        "active": active_metrics,
        "candidate": candidate_metrics,
    }
    evaluation_path = evaluation_dir / "latest_metrics.json"
    shadow_report_path = evaluation_dir / "shadow_comparison_report.json"
    _write_json(evaluation_path, evaluation)
    _write_json(
        shadow_report_path,
        _shadow_report(active_prob, candidate_prob, y_test, threshold=threshold),
    )
    _write_json(evaluation_dir / "feature_baseline.json", baseline_stats)
    registry_path = model_dir / "model_registry.json"
    _write_json(
        registry_path,
        {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "active_model": active_metadata,
            "candidate_model": candidate_metadata,
            "dataset_path": dataset_ref,
        },
    )
    return TrainingArtifacts(
        active_model_path=model_dir / "active" / "model.joblib",
        candidate_model_path=model_dir / "candidate" / "model.joblib",
        evaluation_path=evaluation_path,
        shadow_report_path=shadow_report_path,
        registry_path=registry_path,
        dataset_path=dataset_path,
        dataset_manifest_path=dataset_manifest_path,
    )


def ensure_models(
    *,
    rows: int = 8000,
    seed: int = 42,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    dataset_manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> TrainingArtifacts:
    active_path = MODEL_DIR / "active" / "model.joblib"
    candidate_path = MODEL_DIR / "candidate" / "model.joblib"
    evaluation_path = EVAL_DIR / "latest_metrics.json"
    shadow_report_path = EVAL_DIR / "shadow_comparison_report.json"
    registry_path = MODEL_DIR / "model_registry.json"
    active_metadata_path = MODEL_DIR / "active" / "metadata.json"
    candidate_metadata_path = MODEL_DIR / "candidate" / "metadata.json"
    metadata_keys = {"name", "version", "training_rows", "positive_class_rate"}
    if (
        active_path.exists()
        and candidate_path.exists()
        and evaluation_path.exists()
        and shadow_report_path.exists()
        and registry_path.exists()
        and _json_contains(active_metadata_path, metadata_keys)
        and _json_contains(candidate_metadata_path, metadata_keys)
    ):
        return TrainingArtifacts(
            active_model_path=active_path,
            candidate_model_path=candidate_path,
            evaluation_path=evaluation_path,
            shadow_report_path=shadow_report_path,
            registry_path=registry_path,
            dataset_path=dataset_path,
            dataset_manifest_path=dataset_manifest_path,
        )
    dataframe = generate_synthetic_dataset(rows=rows, seed=seed)
    write_dataset_bundle(
        dataframe,
        seed=seed,
        dataset_path=dataset_path,
        manifest_path=dataset_manifest_path,
    )
    return train_models(
        dataframe,
        dataset_path=dataset_path,
        dataset_manifest_path=dataset_manifest_path,
    )
