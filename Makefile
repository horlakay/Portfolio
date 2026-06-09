SHELL := /bin/sh
PYTHON ?= python
LOCAL_CLUSTER_NAME ?= sentinelstream-local
LOCAL_NAMESPACE ?= sentinelstream
LOCAL_DATA_NAMESPACE ?= sentinelstream-data
LOCAL_RELEASE_NAME ?= sentinelstream
LOCAL_IMAGE_REGISTRY ?= sentinelstream
LOCAL_IMAGE_TAG ?= local
LOCAL_POSTGRES_PASSWORD ?= sentinel
LOCAL_JWT_SECRET ?= local-demo-jwt-secret-2026-please-change
LOCAL_ANALYST_PASSWORD ?= demo-password
LOCAL_DEMO_SERVICES := ingestion-service feature-service rule-engine model-service decision-service feedback-service analyst-console

.PHONY: up down logs lint test validate-delivery benchmark benchmark-model demo demo-data train-models format seed helm-lint helm-template-dev helm-template-local helm-template-prod terraform-dev-init terraform-dev-plan terraform-prod-init terraform-prod-plan chaos-model-timeout chaos-model-reset chaos-feature-latency chaos-cache-disable chaos-feature-reset chaos-redis-down chaos-redis-up chaos-broker-down chaos-broker-up k8s-kind-create k8s-kind-delete k8s-local-build-images k8s-kind-load-images k8s-local-demo-data k8s-local-deploy k8s-local-status k8s-local-demo k8s-local-port-forward k8s-local-up desktop-analyst-install desktop-analyst-dev desktop-analyst-pack

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
	helm lint infra/helm/sentinelstream -f infra/helm/sentinelstream/values-local.yaml
	helm lint infra/helm/sentinelstream -f infra/helm/sentinelstream/values-prod.yaml

helm-template-dev:
	helm template sentinelstream infra/helm/sentinelstream -f infra/helm/sentinelstream/values-dev.yaml

helm-template-local:
	helm template sentinelstream infra/helm/sentinelstream -f infra/helm/sentinelstream/values-local.yaml

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

k8s-kind-create:
	@if ! kind get clusters | grep -qx "$(LOCAL_CLUSTER_NAME)"; then \
		kind create cluster --name "$(LOCAL_CLUSTER_NAME)"; \
	fi

k8s-kind-delete:
	kind delete cluster --name "$(LOCAL_CLUSTER_NAME)"

k8s-local-build-images:
	$(PYTHON) -m training.pipelines.bootstrap_models --rows 12000 --seed 42
	@set -e; \
	for service in $(LOCAL_DEMO_SERVICES); do \
		echo "Building $$service"; \
		docker build -f "services/$$service/Dockerfile" -t "$(LOCAL_IMAGE_REGISTRY)/$$service:$(LOCAL_IMAGE_TAG)" .; \
	done

k8s-kind-load-images:
	@set -e; \
	for service in $(LOCAL_DEMO_SERVICES); do \
		echo "Loading $$service into kind"; \
		kind load docker-image "$(LOCAL_IMAGE_REGISTRY)/$$service:$(LOCAL_IMAGE_TAG)" --name "$(LOCAL_CLUSTER_NAME)"; \
	done

k8s-local-demo-data:
	kubectl create namespace "$(LOCAL_DATA_NAMESPACE)" --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" create secret generic sentinelstream-demo-data --from-literal=POSTGRES_PASSWORD="$(LOCAL_POSTGRES_PASSWORD)" --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" apply -f infra/kubernetes/demo-data/postgres.yaml
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" apply -f infra/kubernetes/demo-data/redis.yaml
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" apply -f infra/kubernetes/demo-data/redpanda.yaml
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" rollout status deployment/sentinelstream-dev-postgres --timeout=10m
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" rollout status deployment/sentinelstream-redis --timeout=5m
	kubectl -n "$(LOCAL_DATA_NAMESPACE)" rollout status deployment/sentinelstream-dev-redpanda --timeout=10m

k8s-local-deploy:
	helm upgrade --install "$(LOCAL_RELEASE_NAME)" infra/helm/sentinelstream \
		--namespace "$(LOCAL_NAMESPACE)" \
		--create-namespace \
		--values infra/helm/sentinelstream/values-local.yaml \
		--set-string global.imageRegistry="$(LOCAL_IMAGE_REGISTRY)" \
		--set-string global.imageTag="$(LOCAL_IMAGE_TAG)" \
		--set-string secrets.stringData.JWT_SECRET="$(LOCAL_JWT_SECRET)" \
		--set-string secrets.stringData.ANALYST_CONSOLE_PASSWORD="$(LOCAL_ANALYST_PASSWORD)" \
		--set-string secrets.stringData.POSTGRES_PASSWORD="$(LOCAL_POSTGRES_PASSWORD)" \
		--debug \
		--wait \
		--timeout 15m

k8s-local-status:
	@echo "=== $(LOCAL_DATA_NAMESPACE) ==="
	kubectl get pods,svc -n "$(LOCAL_DATA_NAMESPACE)"
	@echo "=== $(LOCAL_NAMESPACE) ==="
	kubectl get pods,svc -n "$(LOCAL_NAMESPACE)"

k8s-local-demo:
	kubectl -n "$(LOCAL_NAMESPACE)" exec deployment/$(LOCAL_RELEASE_NAME)-ingestion-service -- python /app/scripts/demo_scenarios.py

k8s-local-port-forward:
	kubectl -n "$(LOCAL_NAMESPACE)" port-forward svc/$(LOCAL_RELEASE_NAME)-analyst-console 8007:8007

k8s-local-up: k8s-kind-create k8s-local-build-images k8s-kind-load-images k8s-local-demo-data k8s-local-deploy

desktop-analyst-install:
	cd apps/analyst-desktop && npm install

desktop-analyst-dev:
	cd apps/analyst-desktop && npm run dev

desktop-analyst-pack:
	cd apps/analyst-desktop && npm run dist

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
