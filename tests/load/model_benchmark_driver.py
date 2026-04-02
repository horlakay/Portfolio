from __future__ import annotations

import json
import os
import statistics
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE_PAYLOAD = json.loads((ROOT / "data" / "samples" / "model_score_request.json").read_text())
RESULTS_PATH = ROOT / "tests" / "load" / "results" / "latest_model_benchmark.json"


def percentile(values: list[float], value: float) -> float:
    index = int(len(values) * value)
    return values[min(max(index, 0), len(values) - 1)]


def main() -> None:
    base_url = os.environ.get("MODEL_SERVICE_URL", "http://model-service:8004")
    iterations = int(os.environ.get("BENCHMARK_RUNS", "100"))
    samples: list[float] = []
    score_gaps: list[float] = []
    divergence_count = 0
    started_suite = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        for index in range(iterations):
            payload = deepcopy(BASE_PAYLOAD)
            payload["event"]["event_id"] = str(uuid4())
            payload["event"]["session_id"] = f"model-bench-session-{index}"
            started = time.perf_counter()
            response = client.post("/v1/model/score", json=payload)
            response.raise_for_status()
            body = response.json()
            divergence_count += int(bool(body.get("divergence")))
            if body.get("candidate_risk_score") is not None:
                score_gaps.append(abs(body["risk_score"] - body["candidate_risk_score"]))
            samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    total_duration = time.perf_counter() - started_suite
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": "model-service",
        "runs": len(samples),
        "divergence_count": divergence_count,
        "avg_score_gap": round(statistics.fmean(score_gaps), 4) if score_gaps else 0.0,
        "throughput_rps": round(len(samples) / total_duration, 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(percentile(samples, 0.95), 2),
        "p99_ms": round(percentile(samples, 0.99), 2),
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
