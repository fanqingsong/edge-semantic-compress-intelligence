# ADR-0003: Edge SLM local inference and constrained output

- Status: Accepted (architecture constraint); model and format undecided
- Date: 2026-11-01
- Related PRD: PRD-02
- Code: [Summarization](../services/edge/summarization.md)

## Context

The edge must turn filtered logs into a structured summary. The system requires low latency, predictable output, and continued local processing when the network is unavailable.

## Decision

- The SLM runs locally on the edge and has at most 3B parameters.
- llama.cpp server is the default inference-service direction in the technical design.
- Generation must be constrained by a JSON Schema or grammar. Following the technical design, the startup configuration must include `--json-schema`, and the API request uses a JSON response format.
- The current code provides an OpenAI-compatible HTTP summarizer and a server-argument builder. Requests use `response_format: {"type":"json_object"}`. The schema is enforced by the server `--json-schema` argument.
- A local script validates IP, port, and error code. A missing value may be backfilled only from the raw log. It must not be invented.
- The edge does not run an embedding model.

## Consequences

- Model load, schema constraint, batch latency, and resource use must be measured on the target hardware.
- The technical design lists both AWQ and GGUF as candidate formats. That does not mean the selected llama.cpp version can load both directly.
- The model file, inference parameters, and schema version must be configurable and traceable on their own.

## Open decisions

- Choose a compatible model and quantization format for the target hardware and llama.cpp version.
- State whether the device supports GPU offload, and how parameters such as `--gpu-layers` are adapted to the hardware.
- Define retry, isolation, and alerting when inference times out, the service is unavailable, or schema validation fails.

## Alternatives

- A cloud-hosted SLM: a network failure cannot guarantee local structured processing on the edge, which misses the local-inference goal.
- No structural constraint, relying on the prompt alone: this cannot meet the 100% JSON-validity requirement. Rejected.
