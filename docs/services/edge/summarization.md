# Summarization

Code: [`services/edge-agent/src/edge/summarization`](../../../services/edge-agent/src/edge/summarization)

Related: [PRD-02](../../prds/prd-02-edge-summarization.md), [ADR-0003](../../adr/adr-0003-edge-slm-runtime.md)

## Responsibilities

Distill the filtered records of one service into a single [`EdgeEvent`](../shared.md). This service does not run embeddings and does not send events.

- `EDGE_SUMMARIZER=mock` uses a deterministic mock for integration without a model.
- `EDGE_SUMMARIZER=llama_cpp` calls a llama.cpp server. The request must include a JSON Schema. The output is not free text.
- Entity validation backfills IP, port, and error code only from the raw logs in the current batch. A value that is not in the logs stays empty. Nothing is invented.
- A port is taken only from an explicit port field or from text that carries a port label.

Summarization depends on the log records produced by filtering. After the event passes validation, it is handed to [transport](transport.md).
