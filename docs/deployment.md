# Deployment

## Deployment Model

SentinelStream uses two runtime modes:

- Local:
  - `docker compose` runs the application, data dependencies, and observability stack on one machine.
- AWS:
  - Terraform provisions the network, EKS cluster, ECR repositories, and an artifact bucket.
  - Helm deploys the application services into EKS.
  - PostgreSQL, Redis, and Kafka-compatible brokers are supplied as external endpoints.

The chart is intentionally focused on the application tier. That keeps the AWS path realistic for a portfolio system:

- application workloads run on EKS
- container images come from ECR
- secrets are injected at deploy time
- data dependencies can be swapped between demo-grade in-cluster services and managed services without rewriting the apps

If you are wiring this project to your own GitHub account, use [docs/github-setup.md](C:/Users/OMEN/Desktop/kayode/SentinelStream/docs/github-setup.md) as the end-to-end bootstrap guide.

## AWS Topology

- VPC with DNS enabled
- two public subnets
- two private subnets
- Internet Gateway and NAT Gateway
- EKS cluster with managed node groups in private subnets
- IRSA-enabled cluster for future service-account IAM bindings
- ECR repositories for each service image
- S3 bucket for future model artifacts, evaluation exports, and benchmark report archival

## Terraform Layout

- `infra/terraform/environments/dev`
  - bootstraps the development VPC, EKS cluster, optional shared ECR repositories, and the dev artifact bucket
- `infra/terraform/environments/prod`
  - provisions the production VPC, EKS cluster, and production artifact bucket
  - defaults `manage_ecr_repositories=false` so prod can reuse a shared registry created by the dev or shared account
- `infra/terraform/modules/network`
  - VPC, subnets, route tables, NAT, and EKS subnet tagging
- `infra/terraform/modules/eks`
  - EKS control plane, managed node group, control plane logs, access entries, and IRSA
- `infra/terraform/modules/ecr`
  - per-service repositories, image scanning, and lifecycle policies
- `infra/terraform/modules/artifact-store`
  - encrypted, versioned S3 bucket for deployment artifacts

## Terraform Commands

Development:

```bash
cd infra/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Production:

```bash
cd infra/terraform/environments/prod
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Helpful Make targets:

```bash
make terraform-dev-init
make terraform-dev-plan
make terraform-prod-init
make terraform-prod-plan
```

Important:

- if GitHub Actions will deploy to EKS, its IAM role ARN must be included in `admin_principal_arns`
- that is what grants the workflow Kubernetes access through the EKS access entries created by Terraform

Repo-only validation when Terraform or Helm binaries are not installed locally:

```bash
make PYTHON=.venv\Scripts\python test
make PYTHON=.venv\Scripts\python validate-delivery
```

`scripts/validate_delivery.py` parses the Terraform modules, environment stacks, Helm values, chart templates, and GitHub Actions workflows so the delivery layer can still be verified in restricted environments and CI preflight checks.

## Kubernetes Packaging

The primary deployment path is the Helm chart in `infra/helm/sentinelstream`.

What the chart does:

- deploys every SentinelStream service as its own Deployment and Service
- injects shared runtime config through a ConfigMap
- consumes a pre-created Kubernetes Secret for sensitive values
- creates a ServiceAccount per service so IRSA can be attached later without chart surgery
- adds liveness and readiness probes on every service
- provisions HPAs and PodDisruptionBudgets for the higher-value services
- exposes the analyst console either through:
  - an internal `LoadBalancer` Service, or
  - an Ingress if your cluster already runs an ingress controller

Current default:

- dev and prod values expose `analyst-console` with an internal AWS NLB-backed `LoadBalancer`
- Ingress support remains available but disabled by default to avoid requiring an ingress controller for the first EKS deployment

## Secret and Config Strategy

SentinelStream splits configuration into three buckets.

Non-secret environment config:

- stored in Helm values or GitHub Environment variables
- examples:
  - `POSTGRES_HOST`
  - `POSTGRES_DB`
  - `POSTGRES_USER`
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `AWS_REGION`
  - `EKS_CLUSTER_NAME`

Secrets:

- stored in GitHub Environment secrets
- rendered into Kubernetes as `sentinelstream-secrets` during deploy
- examples:
  - `JWT_SECRET`
  - `ANALYST_CONSOLE_PASSWORD`
  - `POSTGRES_PASSWORD`
  - `REDIS_URL`

Cloud credentials:

- GitHub Actions uses OIDC plus `aws-actions/configure-aws-credentials`
- no static AWS access keys are required

This keeps secrets out of:

- Git
- Terraform state for application credentials
- Helm values files

## Required GitHub Environment Variables

Set these on the `dev` and `prod` GitHub Environments:

- `AWS_REGION`
- `ECR_REGISTRY`
- `EKS_CLUSTER_NAME`
- `KUBE_NAMESPACE`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `KAFKA_BOOTSTRAP_SERVERS`

Set these as GitHub Environment secrets:

- `AWS_DEPLOY_ROLE_ARN`
- `JWT_SECRET`
- `ANALYST_CONSOLE_PASSWORD`
- `POSTGRES_PASSWORD`
- `REDIS_URL`

## Manual Helm Deployment

After Terraform has created the cluster and the application secret exists:

```bash
aws eks update-kubeconfig --name sentinelstream-dev --region eu-west-1
kubectl create namespace sentinelstream --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install sentinelstream infra/helm/sentinelstream \
  --namespace sentinelstream \
  --create-namespace \
  --values infra/helm/sentinelstream/values-dev.yaml \
  --set-string global.imageRegistry=<account>.dkr.ecr.eu-west-1.amazonaws.com/sentinelstream \
  --set-string global.imageTag=<git-sha> \
  --set-string config.postgres.host=<postgres-host> \
  --set-string config.postgres.port=5432 \
  --set-string config.postgres.database=sentinelstream \
  --set-string config.postgres.user=sentinel \
  --set-string config.kafkaBootstrapServers=<broker-host>:9092 \
  --history-max 10 \
  --atomic \
  --wait \
  --timeout 10m
```

Validate:

```bash
kubectl -n sentinelstream rollout status deployment/sentinelstream-decision-service
kubectl -n sentinelstream get svc sentinelstream-analyst-console
```

## CI/CD Flow

### `ci.yml`

Runs on pull requests and pushes to `main`.

- Python linting and tests
- `compileall`
- Terraform formatting and validation
- Helm lint and render validation
- `pip-audit`
- Trivy filesystem scan

### `deploy.yml`

Runs automatically on pushes to `main`.

- bootstraps model artifacts before image builds
- builds and pushes every service image to ECR
- scans the pushed images with Trivy
- updates the dev cluster via Helm
- runs rollout checks
- runs a post-deploy decision benchmark
- uploads `tests/load/results/latest_benchmark.json` as a workflow artifact

### `promote-prod.yml`

Runs manually.

- accepts a previously built `image_tag`
- reuses the same image set in the prod cluster
- recreates the application secret from prod environment secrets
- deploys with prod values
- waits for rollouts and runs a readiness smoke test

## Local Release Verification

For a full pre-merge check on a workstation with the required CLIs:

```bash
make test
make validate-delivery
make helm-lint
make helm-template-dev
make terraform-dev-plan
```

For restricted shells, `make validate-delivery` is the fallback verification path for the Terraform, Helm, and GitHub Actions assets.

## Rollout Strategy

1. Merge to `main`.
2. `deploy.yml` builds images tagged with `github.sha`.
3. The workflow deploys `dev` with that tag and waits for readiness.
4. The workflow runs a benchmark and publishes the report artifact.
5. After dev validation, trigger `promote-prod.yml` with the same image tag.

This preserves a clean promotion boundary:

- dev proves the exact image set
- prod does not rebuild images
- rollback stays image-tag and Helm-revision based

## Rollback Strategy

Automatic safety:

- Helm upgrades use `--atomic`
- a failed upgrade automatically rolls back the release revision

Manual rollback:

```bash
helm history sentinelstream -n sentinelstream
helm rollback sentinelstream <revision> -n sentinelstream --wait
kubectl -n sentinelstream rollout status deployment/sentinelstream-decision-service
```

Image rollback:

- redeploy a previous known-good image tag through Helm or `promote-prod.yml`

Secret rollback:

- reapply the last-known-good `sentinelstream-secrets` manifest
- restart the affected Deployments if the issue was secret-specific

Model rollback:

- restore the last-known-good model artifact in the model-service image or artifact bundle
- redeploy the previous image tag

## Local vs Cloud Tradeoffs

The local path is intentionally fuller than the initial cloud path:

- local runs Redpanda, Redis, Postgres, Grafana, Tempo, Loki, and Prometheus directly
- cloud focuses first on application delivery to EKS

Recommended cloud follow-ups:

- PostgreSQL:
  - dev: in-cluster Postgres or small RDS instance
  - prod: RDS or Aurora PostgreSQL
- Redis:
  - dev: in-cluster Redis or small ElastiCache
  - prod: ElastiCache with auth
- Kafka-compatible broker:
  - dev: Redpanda in a dedicated namespace or external dev cluster
  - prod: Amazon MSK or managed Redpanda

That split is deliberate. It keeps the repo demoable locally while still presenting a credible AWS delivery story.
