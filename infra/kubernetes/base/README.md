# Kubernetes Base Manifests

The Helm chart in `infra/helm/sentinelstream` is the authoritative deployment path.

The files in this directory are reference snippets only:

- namespace bootstrap examples
- simple config examples
- ingress examples for clusters that already run an ingress controller

Use Helm for real deployments so you keep:

- consistent service names
- shared config and secret wiring
- HPA and PDB management
- rollout history and rollback support
