# GitHub Setup

## Goal

This guide takes SentinelStream from a local folder to:

- a GitHub repository
- GitHub Actions CI/CD
- ECR image publishing
- automated deployment to EKS

The recommended layout is:

- GitHub hosts the code, workflows, docs, and benchmark artifacts
- AWS hosts the running platform

## 1. Create the GitHub Repository

This workspace is not initialized as a Git repository yet, so start here.

```bash
git init
git add .
git commit -m "Initial SentinelStream platform"
git branch -M main
git remote add origin https://github.com/<your-github-user-or-org>/sentinelstream.git
git push -u origin main
```

Recommended repository settings:

- visibility: public if this is primarily for portfolio use
- default branch: `main`
- branch protection on `main`
- require pull request reviews if you want a stronger engineering signal

## 2. Create AWS Deploy Roles for GitHub Actions

Create one role per environment:

- `sentinelstream-github-dev`
- `sentinelstream-github-prod`

GitHub Actions will assume these roles using OIDC. You do not need static AWS keys.

### Trust Policy

Use this trust policy for the `dev` role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:<github-owner>/<repo-name>:environment:dev"
        }
      }
    }
  ]
}
```

Use the same shape for `prod`, changing only the subject:

```json
"token.actions.githubusercontent.com:sub": "repo:<github-owner>/<repo-name>:environment:prod"
```

### IAM Permissions Policy

Attach a permissions policy that allows:

- ECR login and image push
- EKS cluster discovery

Example starter policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:InitiateLayerUpload",
        "ecr:ListImages",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:<region>:<account-id>:repository/sentinelstream/*"
    },
    {
      "Sid": "EksDescribe",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster"
      ],
      "Resource": "arn:aws:eks:<region>:<account-id>:cluster/sentinelstream-*"
    }
  ]
}
```

Important:

- IAM permissions alone are not enough for deployment
- the role must also be granted Kubernetes access through Terraform via `admin_principal_arns`

## 3. Add the GitHub Roles to Terraform

Before applying Terraform, include the deploy role ARN in `admin_principal_arns`.

Example `infra/terraform/environments/dev/terraform.tfvars`:

```hcl
admin_principal_arns = [
  "arn:aws:iam::<account-id>:role/platform-admin",
  "arn:aws:iam::<account-id>:role/sentinelstream-github-dev",
]

node_instance_types = [
  "m7i-flex.large",
]
```

Example `infra/terraform/environments/prod/terraform.tfvars`:

```hcl
admin_principal_arns = [
  "arn:aws:iam::<account-id>:role/platform-admin",
  "arn:aws:iam::<account-id>:role/sentinelstream-github-prod",
]
```

This is what gives the GitHub Actions role EKS access through the cluster access entries created in Terraform.

## 4. Provision AWS Infrastructure

Apply the `dev` environment first:

```bash
cd infra/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform apply
```

If your AWS account is on the free plan, keep the dev node group on `m7i-flex.large` or another free-plan-eligible instance type. Using `t3.large` will fail node-group creation on accounts that restrict launch types to free-plan-eligible instances.

Useful outputs:

```bash
terraform output -raw cluster_name
terraform output -raw artifact_bucket_name
terraform output -json ecr_repository_urls
```

Repeat for `prod` when you are ready.

## 5. Create GitHub Environments

In GitHub:

1. Open your repository
2. Go to `Settings`
3. Go to `Environments`
4. Create:
   - `dev`
   - `prod`

Recommended environment protections:

- `prod`: required reviewers
- `dev`: no reviewers, automatic deploys allowed

## 6. Add GitHub Environment Variables and Secrets

Add these variables to both `dev` and `prod` environments.

| Name | Example | How to get it |
| --- | --- | --- |
| `AWS_REGION` | `eu-west-1` | same value used in Terraform |
| `ECR_REGISTRY` | `123456789012.dkr.ecr.eu-west-1.amazonaws.com` | AWS account ID + region |
| `EKS_CLUSTER_NAME` | `sentinelstream-dev` | `terraform output -raw cluster_name` |
| `KUBE_NAMESPACE` | `sentinelstream` | recommended default |
| `POSTGRES_HOST` | `sentinelstream-dev.cluster-xyz.eu-west-1.rds.amazonaws.com` | your Postgres endpoint |
| `POSTGRES_PORT` | `5432` | your Postgres port |
| `POSTGRES_DB` | `sentinelstream` | your DB name |
| `POSTGRES_USER` | `sentinel` | your DB username |
| `KAFKA_BOOTSTRAP_SERVERS` | `b-1.example.kafka.eu-west-1.amazonaws.com:9092` | your MSK or Redpanda endpoint |

Add these secrets to both environments.

| Name | Notes |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | use the environment-specific GitHub Actions role ARN |
| `JWT_SECRET` | long random secret for analyst/admin auth |
| `ANALYST_CONSOLE_PASSWORD` | internal demo login password |
| `POSTGRES_PASSWORD` | database password |
| `REDIS_URL` | full Redis URL, for example `redis://:<password>@host:6379/0` |

## 7. First Push and Automatic Dev Deployment

Once the repo exists and the environment variables and secrets are configured:

```bash
git checkout -b setup/github-live
git add .
git commit -m "Prepare SentinelStream for GitHub deployment"
git push -u origin setup/github-live
```

Open a pull request, let `CI` pass, then merge to `main`.

What happens on merge:

- `ci.yml` validates code quality, tests, Terraform, Helm, and security checks
- `deploy.yml` builds images
- images are pushed to ECR
- Helm deploys `dev`
- the workflow runs a readiness smoke test and decision benchmark
- the benchmark artifact is uploaded to GitHub Actions

## 8. Production Promotion

After `dev` is healthy, open GitHub Actions and run:

- `Promote Prod`

Provide the `image_tag` from the successful dev deployment. This keeps promotion artifact-based rather than rebuild-based.

## 9. Rollback

If a deployment fails:

- Helm automatically rolls back because deploys use `--atomic`

For manual rollback:

```bash
helm history sentinelstream -n sentinelstream
helm rollback sentinelstream <revision> -n sentinelstream --wait
```

If you need to roll back prod to a previous image:

- rerun `Promote Prod` with the prior known-good `image_tag`

## 10. What to Show Recruiters

Once live, your strongest demo path is:

1. GitHub repository homepage and README
2. Passing GitHub Actions checks
3. Dev deployment workflow run with benchmark artifact
4. Grafana dashboards and traces
5. Analyst console walking through a suspicious decision
6. Manual prod promotion workflow

That combination reads as a real engineering system rather than a code sample.
