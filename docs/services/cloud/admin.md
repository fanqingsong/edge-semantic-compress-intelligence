# Admin

Code: [`services/admin/src/cloud/admin`](../../../services/admin/src/cloud/admin)

Process: `cloud-admin`. The Compose service name is `admin`. It listens on `8088`.

## Responsibilities

This is the operator console for the running cloud path. It has three pages:

- Overview reads edge outbox counts from `GET /v1/status`, counts rows in `processed.sqlite3` and `analyses.sqlite3`, and counts cases in Milvus.
- Analyses lists and opens RAG results stored by the [cloud agent](agent.md).
- Knowledge lists case fields and uploads one operations document for import.

The console does not review prompt suggestions, change edge filter rules, delete individual cases, or edit stored analyses. Publishing a prompt is still outside this process.

Imports call the same [knowledge ingestion](knowledge.md) parser and ingestor used by `knowledge-ingest`. The upload filename is the case `source`. Uploading that filename again replaces stale cases for that source. One import runs at a time. The job record lives in the admin SQLite file, not in `analyses.sqlite3`.

## HTTP

`GET /healthz` and the HTML pages do not require a token. Every `/api/*` route requires `Authorization: Bearer ${ADMIN_TOKEN}`. The process exits when `ADMIN_TOKEN` is empty.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/status` | Edge reachability, outbox counts, processed and analysis counts, case count, latest import |
| `GET` | `/api/analyses?limit=&before=` | Analysis list, newest first |
| `GET` | `/api/analyses/{event_id}` | One analysis and its retrieved cases |
| `GET` | `/api/cases?target_ip=&source=&limit=` | Scalar case fields, without embeddings |
| `POST` | `/api/knowledge/documents` | Upload one Markdown, TXT, JSONL, PDF, DOCX, PPTX, or HTML file up to 20 MiB |
| `GET` | `/api/knowledge/jobs/{id}` | `queued`, `running`, `succeeded`, or `failed` |

Analysis and processed files are opened with `mode=ro`. A missing file or an unreachable edge is reported as unavailable; the page still opens. The edge status payload is only `pending_count` and `pending_bytes`.

The browser keeps the token in `sessionStorage` for the local console. Set `ADMIN_TOKEN` in `.env` before starting Compose.

## Boundaries

The admin process does not join the Kafka consumer and does not mount the edge outbox volume. It calls the edge agent over HTTP. Retrieval's online `search` contract is unchanged; case browsing uses `list_cases`.
