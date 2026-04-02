# ADR 0001: Event-Driven Online and Offline Split

## Status

Accepted

## Context

Fraud platforms need immediate decisions while preserving replayable history for investigation and model iteration.

## Decision

Use Redpanda as the event backbone, with synchronous online scoring exposed through `decision-service`.

## Consequences

- supports replayable state updates and realistic platform design
- adds operational complexity versus a single synchronous API
- better demonstrates backend and SRE depth for portfolio purposes

