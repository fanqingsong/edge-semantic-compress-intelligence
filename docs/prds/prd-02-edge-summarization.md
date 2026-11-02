# PRD-02: Edge SLM structured distillation and entity validation

**Original requirements:** E-03, E-04

**Service:** [Summarization](../services/edge/summarization.md)

## Goal

Distill rule-filtered logs, in batches, into a stable and smaller structured summary, and validate critical entities before sending.

## Scope

- Call a local SLM of at most 3B parameters to summarize a log batch.
- Force structured output through llama.cpp server `--json-schema`. Call `/v1/chat/completions` and request JSON object format.
- Validate entities such as IP, port, and error code. When one is missing, extract it from the raw log with a regular expression and fill it in.
- Hand the validated structured record to the secure transport module.
- Do not deploy an embedding model on the edge.

## Data contract

The MVP uses [event schema v1.0 defined in ADR-0009](../adr/adr-0009-edge-event-contract.md). `event_id`, a timezone-aware `timestamp`, `service`, and `summary` are required. `target_ip`, `target_port`, and `error_code` may be omitted or empty. An event does not contain the raw log. Unknown fields are rejected. An entity may come only from the SLM or from backfill against the raw log. It must not be invented. A port must be an integer from 1 to 65535.

This contract is the agreement for the first implementation. If the business confirms that extra fields or raw-log transport are required, update the ADR and the schema version policy first.

## Acceptance criteria

- Every successful output matches the versioned JSON Schema. JSON validity is 100%.
- Per-batch latency is under 2 seconds. The test batch size and the target hardware are fixed and recorded.
- On the agreed entity-labeled test set, at least 99% of critical entity fields are complete.
- A field that cannot be backfilled from the raw log is marked missing by the agreed rule. It is not fabricated.
- On the target device, SLM video memory stays under 2 GB and whole-device power stays under 30 W.

## Dependencies and open decisions

- Depends on the log batches and raw-log references produced by PRD-01.
- The technical design requires llama.cpp server and `--json-schema`. The constraint must be verified on the selected version and the target hardware.
- Choose a model format compatible with the runtime from the AWQ and GGUF candidates. Define retry or fallback behavior for timeout, model unavailability, and schema validation failure.
- Correct and test the regular expressions for IP, port, and error code. State whether IPv6 is in scope for this phase.
