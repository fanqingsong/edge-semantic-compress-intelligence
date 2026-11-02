# Filtering

Code: [`services/edge-agent/src/edge/filtering`](../../../services/edge-agent/src/edge/filtering)

Related: [PRD-01](../../prds/prd-01-edge-ingestion-filtering.md), [ADR-0002](../../adr/adr-0002-edge-collector.md)

## Responsibilities

Apply rule-only filtering to a log batch. This service does not call a model and does not run embeddings. Records that pass are handed to [summarization](summarization.md) grouped by service.

The rule order is fixed:

1. L1 format check. Drop reason: `invalid_format`.
2. L2 success status. Drop `200` or `ok`. Reason: `success_status`.
3. L3 keyword denylist. Drop heartbeats and health checks. Reason: `blacklisted_keyword`.
4. L4 rate suppression. For the same service and the same message above the threshold, keep only the first and last occurrence. Reason: `frequency_suppressed`.

Collection is not in this package. Fluent Bit reads files and receives syslog on UDP `5514`. After normalization it hands the log batch to the [edge agent](agent.md). Configuration is in [`deploy/fluent-bit`](../../../deploy/fluent-bit).
