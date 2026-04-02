# Benchmark Results

`benchmark_driver.py` writes the latest local decision benchmark snapshot to `latest_benchmark.json`.

`model_benchmark_driver.py` writes the latest local model-service latency snapshot to `latest_model_benchmark.json`.

`deploy.yml` uploads the latest post-deploy decision benchmark as a GitHub Actions artifact named `decision-benchmark-<git-sha>`.

Use these outputs for:

- local performance snapshots during development
- release-to-release latency comparison
- recruiter demo evidence tied to a specific image tag
