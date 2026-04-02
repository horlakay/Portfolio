# ADR 0003: Shared ECR and Helm-Based Release Promotion

## Status

Accepted

## Context

SentinelStream needs a deployment path that is:

- realistic enough to discuss in platform and SRE interviews
- simple enough to run as a portfolio project
- compatible with both local demos and AWS deployment

Two friction points showed up quickly:

1. building separate images per service is useful for service ownership and faster rollbacks
2. rebuilding images during prod promotion weakens provenance and complicates rollback

## Decision

Use:

- one ECR repository path per service
- automatic image build and push on merge to `main`
- automatic dev deployment from the pushed image tag
- manual prod promotion by reusing the exact existing image tag
- Helm as the release layer for environment-specific configuration and rollout history

Prod Terraform defaults `manage_ecr_repositories=false` so the production cluster can consume a shared registry without duplicating repository creation in the same AWS account.

## Consequences

Positive:

- release promotion is image-tag based rather than rebuild based
- Helm revision history gives a straightforward rollback path
- environment-specific configuration is separated cleanly from image creation
- the deployment story is easy to explain and defend in interviews

Negative:

- shared ECR requires explicit documentation when dev and prod use different AWS accounts
- data-plane services still need separate provisioning or managed-service endpoints
- GitHub Environment configuration becomes part of the operational contract
