SHELL := /bin/sh
PYTHON ?= python

.PHONY: up down logs lint test validate-delivery benchmark benchmark-model demo demo-data train-models format seed helm-lint helm-template-dev helm-template-prod terraform-dev-init terraform-dev-plan terraform-prod-init terraform-prod-plan chaos-model-timeout chaos-model-reset chaos-feature-latency chaos-cache-disable chaos-feature-reset chaos-redis-down chaos-redis-up chaos-broker-down chaos-broker-up

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy shared/src services training

format:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) scripts/run_pytest.py -q

validate-delivery:
	$(PYTHON) scripts/validate_delivery.py

helm-lint:
	helm lint infra/helm/sentinelstream -f infra/helm/sentinelstream/values-dev.yaml
	helm lint infra/helm/sentinelstream -f infra/helm/sentinelstream/values-prod.yaml

helm-template-dev:
	helm template sentinelstream infra/helm/sentinelstream -f infra/helm/sentinelstream/values-dev.yaml

helm-template-prod:
	helm template sentinelstream infra/helm/sentinelstream -f infra/helm/sentinelstream/values-prod.yaml

terraform-dev-init:
	cd infra/terraform/environments/dev && terraform init

terraform-dev-plan:
	cd infra/terraform/environments/dev && terraform plan

terraform-prod-init:
	cd infra/terraform/environments/prod && terraform init

terraform-prod-plan:
	cd infra/terraform/environments/prod && terraform plan

benchmark:
	docker compose run --rm decision-service python tests/load/benchmark_driver.py

benchmark-model:
	docker compose run --rm model-service python tests/load/model_benchmark_driver.py

demo:
	docker compose run --rm ingestion-service python scripts/demo_scenarios.py

demo-data:
	docker compose run --rm ingestion-service python scripts/demo_scenarios.py

train-models:
	$(PYTHON) -m training.pipelines.bootstrap_models

seed:
	docker compose run --rm ingestion-service python scripts/seed_synthetic_data.py

chaos-model-timeout:
	docker compose exec model-service python scripts/admin_fault.py --target model --delay-ms 250 --error-rate 0.0

chaos-model-reset:
	docker compose exec model-service python scripts/admin_fault.py --target model --delay-ms 0 --error-rate 0.0

chaos-feature-latency:
	docker compose exec feature-service python scripts/admin_fault.py --target feature --delay-ms 120 --error-rate 0.0

chaos-cache-disable:
	docker compose exec feature-service python scripts/admin_fault.py --target feature --delay-ms 0 --cache-enabled false

chaos-feature-reset:
	docker compose exec feature-service python scripts/admin_fault.py --target feature --delay-ms 0 --cache-enabled true

chaos-redis-down:
	docker compose stop redis

chaos-redis-up:
	docker compose up -d redis

chaos-broker-down:
	docker compose stop redpanda

chaos-broker-up:
	docker compose up -d redpanda
