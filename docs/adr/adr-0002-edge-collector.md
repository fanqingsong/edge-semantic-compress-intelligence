# ADR-0002: Edge collection and pre-filter engine

- Status: Accepted (default)
- Date: 2026-11-01
- Related PRD: PRD-01
- Code: [Filtering](../services/edge/filtering.md). Collection configuration is in `deploy/fluent-bit`.

## Context

The edge must collect file and syslog logs and run four low-cost rule layers. Devices are resource constrained, and the system needs checkpoint resume, disk buffering, and Prometheus metrics.

## Decision

- Use Fluent Bit by default as the edge collection and pre-filter engine.
- Filter in this order: L1 format check, L2 status-code filter, L3 keyword denylist, L4 rate suppression.
- Use filesystem buffering for local backlog while disconnected. Filtering does not use AI or embedding plugins.
- Expose CPU, memory, throughput, and filter-count metrics as required by PRD-01.
- Switch to Vector only when the user explicitly asks for it.

## Consequences

- Configuration, filter rules, and deployment examples are written for Fluent Bit first.
- Plugin compatibility, resource use, log rotation, and checkpoint recovery must be verified on the target device.
- Filter thresholds and the expected block rate belong in configuration comments and are checked against the test set.

## Alternatives

- Vector: suitable when rules are complex and VRL expressiveness is needed. It is not the default implementation.
- A custom collector: it would reimplement mature collection, buffering, and monitoring. Not adopted at this stage.
