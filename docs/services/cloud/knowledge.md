# Knowledge ingestion

Code: [`services/knowledge-ingest/src/cloud/knowledge`](../../../services/knowledge-ingest/src/cloud/knowledge)

Process: `knowledge-ingest`. The service name in the Compose profile `tools` is `knowledge-ingest`. It does not stay up on the online fault-analysis path.

Related: [PRD-04](../../prds/prd-04-knowledge-ingestion.md), [ADR-0005](../../adr/adr-0005-knowledge-platform.md)

## Responsibilities

Read operations documents or historical cases, parse them into cases that carry `target_ip`, and call the vector-write interface of the [retrieval](retrieval.md) service to write the Milvus collection `ops_cases`. The vector dimension is 1024.

- JSON Lines is supported, as are Markdown, TXT, PDF, DOCX, PPTX, and HTML. The latter group is converted with MarkItDown.
- A document must explicitly contain `Summary` and `Resolution`. Missing fields fail the import. A model does not fill in facts.
- Embeddings use bge-m3 over HTTP, or the deterministic mock provided by the retrieval service.
- The IP field used at ingestion is the same field used by the online retrieval filter.

Samples are in [examples/knowledge](../../../examples/knowledge/README.md). The import command is in [local development](../../local-development.md).
