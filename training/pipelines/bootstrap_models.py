from __future__ import annotations

import argparse
from pathlib import Path

from training.pipelines.common import DEFAULT_DATASET_PATH, DEFAULT_MANIFEST_PATH, ensure_models


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap models and synthetic dataset if missing."
    )
    parser.add_argument("--rows", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    artifacts = ensure_models(
        rows=args.rows,
        seed=args.seed,
        dataset_path=args.dataset,
        dataset_manifest_path=args.manifest,
    )
    print(f"active model ready at {artifacts.active_model_path}")
    print(f"candidate model ready at {artifacts.candidate_model_path}")
    print(f"evaluation report at {artifacts.evaluation_path}")
    print(f"shadow comparison report at {artifacts.shadow_report_path}")
    print(f"model registry at {artifacts.registry_path}")


if __name__ == "__main__":
    main()
