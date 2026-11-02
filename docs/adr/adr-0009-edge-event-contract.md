# ADR-0009: Edge event schema and data minimization

- Status: Accepted (MVP)
- Date: 2026-11-01
- Related PRDs: PRD-02, PRD-03, PRD-05
- Code: [shared](../services/shared.md)

## Context

The edge SLM, the transport layer, and cloud retrieval need a shared stable data contract. Raw logs may contain sensitive information, and a message needs a stable identifier so retries after a disconnect can be handled idempotently.

## Decision

- The MVP defines `EdgeEvent` schema version `1.0`. The machine-readable contract is `schemas/edge-event-v1.schema.json`.
- `event_id` is a UUID. It is the event identifier and a candidate idempotency key for later transport.
- Required fields: `event_id`, `schema_version`, a timezone-aware ISO 8601 `timestamp`, a non-empty `service`, and a non-empty `summary`.
- Optional fields: `target_ip`, `target_port`, and `error_code`. They may be omitted or set to `null`. A non-empty `target_ip` must be a valid IPv4 or IPv6 address. `target_port` must be an integer from 1 to 65535.
- A port is extracted only from an explicit `port` or `target_port` field, or from a raw-log pattern that names the field, so numbers inside timestamps and error codes are not mistaken for ports.
- Undeclared fields are rejected. The event does not contain the raw log. A missing entity is backfilled only from the local raw log and must not be invented.
- A schema change updates the version and the compatibility tests. The meaning of a v1.0 field must not change silently.

## Consequences

- After local validation and entity backfill, the edge sends only a structured summary to the cloud, which reduces the risk of raw logs leaving the device.
- Cloud retrieval can use `target_ip` and `summary` directly. Fallback retrieval when there is no IP is still decided by ADR-0006.
- `event_id` provides an identity for the event. The transport layer still has to define acknowledgement, duplicate delivery, and idempotent storage.
- This MVP contract does not cover every operations scenario. If the business requires sending the original text or adding fields, assess privacy, size, and version compatibility first.

## Alternatives

- Also transmit the raw log: the cloud can re-parse it, but sensitive-data exposure and bandwidth cost increase. Not used in the MVP.
- No stable event identifier: retries and duplicate messages cannot be handled reliably. Rejected.
