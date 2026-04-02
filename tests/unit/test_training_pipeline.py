from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from training.pipelines.common import (
    FEATURE_COLUMNS,
    generate_synthetic_dataset,
    train_models,
    write_dataset_bundle,
)

ROOT = Path(__file__).resolve().parents[2]


def _workspace_artifact_dir() -> Path:
    artifact_dir = ROOT / "tests" / ".artifacts" / f"training-{uuid4().hex}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def test_synthetic_dataset_contains_expected_columns() -> None:
    dataframe = generate_synthetic_dataset(rows=128, seed=7)
    for column in FEATURE_COLUMNS:
        assert column in dataframe.columns
    assert "label" in dataframe.columns


def test_dataset_bundle_writes_manifest() -> None:
    tmp_path = _workspace_artifact_dir()
    try:
        dataframe = generate_synthetic_dataset(rows=32, seed=11)
        dataset_path = tmp_path / "synthetic.csv"
        manifest_path = tmp_path / "synthetic_manifest.json"
        write_dataset_bundle(
            dataframe,
            seed=11,
            dataset_path=dataset_path,
            manifest_path=manifest_path,
        )
        assert dataset_path.exists()
        assert manifest_path.exists()
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_train_models_writes_registry_and_reports() -> None:
    tmp_path = _workspace_artifact_dir()
    try:
        dataframe = generate_synthetic_dataset(rows=256, seed=17)
        dataset_path = tmp_path / "synthetic.csv"
        manifest_path = tmp_path / "synthetic_manifest.json"
        model_dir = tmp_path / "models"
        evaluation_dir = tmp_path / "evaluation"
        write_dataset_bundle(
            dataframe,
            seed=17,
            dataset_path=dataset_path,
            manifest_path=manifest_path,
        )
        artifacts = train_models(
            dataframe,
            dataset_path=dataset_path,
            dataset_manifest_path=manifest_path,
            model_dir=model_dir,
            evaluation_dir=evaluation_dir,
        )
        registry = json.loads(artifacts.registry_path.read_text(encoding="utf-8"))
        metrics = json.loads(artifacts.evaluation_path.read_text(encoding="utf-8"))
        assert artifacts.active_model_path.exists()
        assert artifacts.candidate_model_path.exists()
        assert registry["active_model"]["name"] == "fraud-gbt"
        assert registry["candidate_model"]["name"] == "fraud-rf-shadow"
        assert metrics["dataset_manifest_path"].endswith("synthetic_manifest.json")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
