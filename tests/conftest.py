from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRA_PATHS = [
    ROOT / "shared" / "src",
    ROOT / "services" / "ingestion-service" / "src",
    ROOT / "services" / "feature-service" / "src",
    ROOT / "services" / "rule-engine" / "src",
    ROOT / "services" / "model-service" / "src",
    ROOT / "services" / "decision-service" / "src",
    ROOT / "services" / "feedback-service" / "src",
    ROOT / "services" / "analyst-console" / "src",
    ROOT,
]

for path in EXTRA_PATHS:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-for-sentinelstream-suite-1234")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
