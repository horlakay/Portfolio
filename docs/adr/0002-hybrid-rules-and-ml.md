# ADR 0002: Hybrid Rules and ML Decisioning

## Status

Accepted

## Context

Pure rules are easy to audit but miss blended behavior patterns. Pure ML is harder to explain and govern.

## Decision

Use deterministic rules for hard controls and an ML model for probabilistic scoring, with shadow candidate evaluation.

## Consequences

- produces interview-defensible decision rationale
- supports safe model iteration
- requires careful threshold tuning and degraded fallback design

