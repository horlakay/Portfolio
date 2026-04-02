from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from training.pipelines.common import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MANIFEST_PATH,
    train_models,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train SentinelStream active and shadow models.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    dataframe = pd.read_csv(args.dataset)
    artifacts = train_models(
        dataframe,
        dataset_path=args.dataset,
        dataset_manifest_path=args.manifest,
    )
    print(f"trained active model: {artifacts.active_model_path}")
    print(f"trained candidate model: {artifacts.candidate_model_path}")
    print(f"evaluation report: {artifacts.evaluation_path}")
    print(f"shadow report: {artifacts.shadow_report_path}")
    print(f"model registry: {artifacts.registry_path}")


if __name__ == "__main__":
    main()
