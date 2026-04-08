# Demo Data Services

This overlay deploys a demo-grade data stack into EKS so SentinelStream can be
shown live without provisioning managed PostgreSQL, Redis, or Kafka first.

Deliberate simplifications:

- PostgreSQL is single-instance and uses ephemeral storage.
- Redis runs as a single non-persistent pod.
- Redpanda runs as a single development broker without persistent storage.

These manifests are for demos and portfolio walkthroughs, not production.

## Apply

Create the shared secret first:

```bash
kubectl create namespace sentinelstream-data --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sentinelstream-data create secret generic sentinelstream-demo-data \
  --from-literal=POSTGRES_PASSWORD='<choose-a-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k infra/kubernetes/demo-data
kubectl -n sentinelstream-data rollout status deployment/sentinelstream-dev-postgres --timeout=10m
kubectl -n sentinelstream-data rollout status deployment/sentinelstream-redis --timeout=5m
kubectl -n sentinelstream-data rollout status deployment/sentinelstream-dev-redpanda --timeout=10m
```

## Service Endpoints

- PostgreSQL: `sentinelstream-dev-postgres.sentinelstream-data.svc.cluster.local:5432`
- Redis: `sentinelstream-redis.sentinelstream-data.svc.cluster.local:6379`
- Redpanda/Kafka: `sentinelstream-dev-redpanda.sentinelstream-data.svc.cluster.local:9092`

## Suggested GitHub Environment Values

- `POSTGRES_HOST=sentinelstream-dev-postgres.sentinelstream-data.svc.cluster.local`
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=sentinelstream`
- `POSTGRES_USER=sentinel`
- `REDIS_URL=redis://sentinelstream-redis.sentinelstream-data.svc.cluster.local:6379/0`
- `KAFKA_BOOTSTRAP_SERVERS=sentinelstream-dev-redpanda.sentinelstream-data.svc.cluster.local:9092`
