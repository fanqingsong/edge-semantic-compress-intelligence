# PRD-01: Edge log collection and rule pre-filtering

**Original requirements:** E-01, E-02

**Service:** [Filtering](../services/edge/filtering.md). Collection configuration is in `deploy/fluent-bit`. Rule filtering is in `services/edge/filtering`.

## Goal

Reliably collect logs from configured sources on a resource-constrained edge device, and use deterministic rules to drop low-value logs so later structured distillation keeps high-value input.

## Users and scenarios

An edge operator configures a log file path or a syslog source. The system collects logs continuously and resumes from the recorded position after a restart or a short failure.

## Scope

- Support a configured file path and syslog.
- Support resume from a checkpoint and persistence of collection state.
- Run four rule layers in order: L1 format check, L2 status-code filter, L3 keyword denylist, and L4 rate suppression.
- The rule layer does not call AI and does not load an embedding model.
- Expose CPU, memory, throughput, and filter-count metrics for the pre-filter engine.

## Acceptance criteria

- Both file and syslog sources can be collected. After a restart, processing continues from the saved position.
- Within the agreed fault-injection and storage-capacity range, collected logs are neither lost nor processed twice. Behavior outside that range is recorded explicitly.
- L1 through L4 can each be configured and tested on their own. Drop reasons are countable.
- On a labeled test set agreed by both sides, at least 90% of invalid logs are blocked.
- Pre-filter engine memory stays under 50 MB. Prometheus metrics can be scraped.

## Dependencies and open decisions

- The technical design defaults to Fluent Bit. Switch to Vector only when the user explicitly asks for it.
- Define the log format, status-code recognition, how the denylist is maintained, the rate window, and the exact behavior of keeping only the first and last occurrence.
- Agree on file rotation, syslog disconnects, disk exhaustion, and configuration hot-reload.
