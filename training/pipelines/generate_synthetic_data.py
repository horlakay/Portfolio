from __future__ import annotations

import argparse
from pathlib import Path

from training.pipelines.common import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MANIFEST_PATH,
    generate_synthetic_dataset,
    write_dataset_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SentinelStream synthetic fraud data.")
    parser.add_argument("--rows", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    dataframe = generate_synthetic_dataset(rows=args.rows, seed=args.seed)
    write_dataset_bundle(
        dataframe,
        seed=args.seed,
        dataset_path=args.output,
        manifest_path=args.manifest,
    )
    print(f"wrote dataset to {args.output}")
    print(f"wrote manifest to {args.manifest}")


if __name__ == "__main__":
    main()
