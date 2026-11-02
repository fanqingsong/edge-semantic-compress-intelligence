# ADR-0005: Cloud knowledge ingestion and vector storage

- Status: Accepted (MVP default: bge-m3 + Milvus + MarkItDown)
- Date: 2026-11-01
- Related PRD: PRD-04
- Code: [Knowledge ingestion](../services/cloud/knowledge.md). The vector-write interface is in [Retrieval](../services/cloud/retrieval.md).

## Context

The cloud must keep parsing operations documents and historical tickets, embed them, and support incremental updates, so hybrid retrieval has data to search. The technical design lists several parsers and vector stores.

## Current architecture constraints

- Document cleaning, parsing, and embedding all run in the cloud.
- Knowledge data supports incremental updates and keeps source traceability.
- The technical design recommends bge-m3. Document-parsing candidates are Unstructured and MarkItDown. Vector-store candidates are Milvus 2.x and Elasticsearch 8.x or newer.
- Raw Markdown and TXT are parsed by deterministic fields. PDF, DOCX, PPTX, and HTML are converted to Markdown with MarkItDown, then case fields are extracted.
- A document must explicitly contain `Summary` and `Resolution`. A document that does not match the structure fails. A model does not guess or generate knowledge facts.

## Decision

- The MVP default stack is a bge-m3 embedding service and Milvus. Keep the `TextEmbedder` and `VectorIndex` adapter boundaries so they can be replaced later.
- The `knowledge-ingest` CLI can parse JSONL, Markdown, TXT, and the PDF, DOCX, PPTX, and HTML formats supported by MarkItDown, and write them to Milvus incrementally.
- The current code provides a bge-m3 HTTP client, a Milvus `VectorIndex` adapter, and a collection initializer. Initialization creates a missing collection and rejects an existing collection whose required fields or vector dimension do not match.
- The Milvus collection needs `case_id` (primary key), `summary`, `resolution`, `source`, `target_ip`, `version`, and an `embedding` vector field. The default vector dimension is 1024 and must match the actual model output.
- `embedding` uses the COSINE metric and AUTOINDEX. Collection initialization does not start the Milvus service and does not replace production backup or migration.
- A local Milvus 2.5.4 integration test has verified collection creation, vector upsert, exact `target_ip` filtered retrieval, and source-level deletion.

## Follow-up configuration

- Expand coverage of raw document formats and the parsing-accuracy evaluation set. There is no OCR today, and arbitrary prose without explicit case fields is not split into cases automatically.
- Confirm the real bge-m3 deployment, vector dimension, index parameters, collection creation, and upgrade migration.
- Define incremental updates, duplicate-document detection, delete propagation, failure retry, and full rebuild.
- Define the evaluation set, sampling method, and labeling standard for the parsing-accuracy target of at least 95%.

## Consequences

- The filter fields and recall capability of PRD-05 depend on the metadata structure and index capability decided here.
- Replacing the embedding model or the vector store requires an assessment of vector recomputation, index migration, and retrieval-quality regression.

## Candidates

- Milvus: a dedicated vector database.
- Elasticsearch: can reuse existing search infrastructure and also carry metadata retrieval.
