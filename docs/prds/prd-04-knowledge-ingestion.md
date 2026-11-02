# PRD-04: Cloud knowledge ingestion

**Original requirement:** C-01

**Service:** [Knowledge ingestion](../services/cloud/knowledge.md)

## Goal

Clean, parse, and embed operations documents and historical tickets, and maintain a knowledge base that can be updated incrementally and used for retrieval.

## Scope

- Import operations documents and historical tickets on a schedule.
- Support JSONL, Markdown, and TXT. PDF, DOCX, PPTX, and HTML are converted with MarkItDown. Markdown cases use explicit `Summary` and `Resolution` fields. `Root cause` and `Target IP` are optional.
- Clean and parse content, and keep the metadata required for retrieval.
- Embed with a cloud embedding model and write the vectors to vector storage.
- Mark versions with a content hash. Upsert new records by source, and remove cases for that source that no longer exist.
- Create a missing Milvus collection at startup, and check the fields and embedding dimension of an existing collection.
- Support incremental updates so content is not imported twice and deleted or updated content is not left behind.

## Acceptance criteria

- Configured knowledge sources are imported on schedule, including new and updated content.
- On a document-parsing evaluation set agreed by both sides, parsing accuracy is at least 95%.
- Every stored record can be traced to its source document and version. A parse or embedding failure can be located and retried.
- Embedding happens only in the cloud. The knowledge base can supply retrieval data to PRD-05.

## Dependencies and open decisions

- The MVP defaults to a bge-m3 embedding service and Milvus. The `knowledge-ingest` CLI can recursively import supported documents from a directory.
- MarkItDown conversion does not guarantee that semantic fields are complete. A document missing required fields fails. It must be arranged to the case template.
- Before locking the design, evaluate document types, permission filters, data deletion, the incremental cursor, and the rebuild strategy.
- Define the denominator, sampling method, and human labeling standard for parsing accuracy, plus source-document access control and sensitive-information handling.
