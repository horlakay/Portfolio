# Benchmarking

## Methodology

- benchmark target: `decision-service`
- scenario: synchronous scoring of a suspicious `transaction_initiated` event
- harnesses:
  - `tests/load/benchmark_driver.py` for lightweight local snapshots
  - `tests/load/model_benchmark_driver.py` for direct model-service latency snapshots
  - `tests/load/k6_decision.js` for repeatable latency assertions
  - benchmark requests generate unique event IDs so decision deduplication does not skew latency lower than the real scoring path
- local stack: Docker Compose with Postgres, Redis, Redpanda, and observability components enabled

## Report Outputs

- local benchmark driver output:
  - `tests/load/results/latest_benchmark.json`
- local model benchmark output:
  - `tests/load/results/latest_model_benchmark.json`
- CI deployment artifact:
  - `deploy.yml` uploads `decision-benchmark-<git-sha>` after the dev deployment smoke benchmark
- GitHub Actions summary:
  - the dev deployment workflow writes the benchmark JSON into the workflow summary for quick review

## Hardware Assumptions

- modern laptop or workstation
- 4+ CPU cores available to Docker
- 8+ GB RAM available to the local stack

## Target Results

- p50 `< 35 ms`
- p95 `< 75 ms`
- p99 `< 150 ms`
- low single-digit error rate under injected dependency faults

## How to Run

```bash
make up
make train-models
make benchmark
make benchmark-model
```

Latest local benchmark output is written to:

- `tests/load/results/latest_benchmark.json` for the full decision-service path
- `tests/load/results/latest_model_benchmark.json` for direct model-service scoring

## Cloud Validation Path

The deployment pipeline includes a post-deploy benchmark:

1. deploy `dev`
2. port-forward `decision-service`
3. run `benchmark_driver.py`
4. upload the resulting JSON artifact

That makes the benchmark story operational instead of static:

- the report is tied to a real image tag
- the benchmark runs against the actual dev release
- the artifact can be attached to recruiter demos or pull request evidence

## Decision Benchmark Fields

- `generated_at`
- `target`
- `runs`
- `success_count`
- `degraded_count`
- `throughput_rps`
- `p50_ms`
- `p95_ms`
- `p99_ms`

Interpretation:

- `degraded_count > 0`
  - the benchmark crossed a dependency fallback path and should be reviewed alongside Grafana and service logs
- `p95_ms > 75`
  - the system missed the local target and should be investigated before using the run as a portfolio benchmark snapshot
- `throughput_rps`
  - is most useful for comparing revisions under the same hardware and dependency profile

For `k6`:

```bash
k6 run tests/load/k6_decision.js
```

## Tradeoffs

- local benchmarks are sensitive to Docker Desktop resource allocation.
- Redis and Redpanda contention can skew latency more than raw model inference time.
- model-only latency is lower than end-to-end decision latency because it excludes feature lookup, rule evaluation, and persistence overhead.
- the portfolio goal is not absolute throughput leadership; it is credible, observable latency behavior under realistic service boundaries.
- cloud benchmark numbers are only comparable when the dependency topology and node sizing remain stable across runs.
