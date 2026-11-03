# Requirements: edge log compression and cloud RAG

The implementation is split by service. The mapping is in the [service catalog](services/README.md). This page keeps the original requirement IDs.

## 1. Background

Build an AIOps log analysis system that combines structured compression on the edge with a decoupled RAG pipeline in the cloud. The edge pre-filters logs and distills them with an SLM. The cloud runs high-precision vector retrieval and root-cause reasoning. The result is a fault-diagnosis loop with low bandwidth, low latency, and high precision.

## 2. Functional requirements

### 2.1 Edge

| ID | Module | Description | Acceptance criteria |
| :--- | :--- | :--- | :--- |
| E-01 | Log collection | Collect raw logs from a configured file path or syslog | No log loss; resume from the last checkpoint |
| E-02 | Rule pre-filter | L1 format check, L2 status-code filter, L3 keyword denylist, L4 rate suppression | Rules only, with no AI cost; at least 90% of invalid logs are blocked |
| E-03 | SLM structured distillation | Send filtered log batches to a local SLM and emit a structured summary that matches a JSON Schema | 100% valid JSON; per-batch latency under 2s |
| E-04 | Entity validation fallback | Validate IP, port, and error code in the SLM output with regular expressions, and fill missing values | At least 99% of critical entity fields are complete |
| E-05 | Secure transport | Send the structured event to the cloud over MQTT or Kafka | Topic ACL by MQTT username; local disk buffering with no data loss on a weak network |

### 2.2 Cloud

| ID | Module | Description | Acceptance criteria |
| :--- | :--- | :--- | :--- |
| C-01 | Knowledge ingestion pipeline | Periodically clean operations documents and historical tickets, embed them with a cloud embedding model, and store the vectors | Incremental updates; document parsing accuracy of at least 95% |
| C-02 | Hybrid retrieval | Exact filter on `target_ip` from the edge JSON, plus vector similarity search on `summary` | Top-5 recall of relevant cases of at least 85% |
| C-03 | RAG reasoning | Assemble retrieved cases and the edge summary into a prompt, then call a large model for root-cause analysis and remediation suggestions | Response time under 10s; actionability score of at least 4/5 |
| C-04 | Feedback loop | Mark cases where the edge summary is insufficient, and generate prompt-optimization suggestions that flow back to the edge | At least 3 valid prompt-iteration suggestions per week |

## 3. Non-functional requirements

- **Edge resource limits**: pre-filter engine memory under 50 MB; SLM video memory under 2 GB; whole-device power under 30 W.
- **Deterministic output**: the edge SLM must be constrained by a JSON Schema or grammar. Free-text generation is not allowed.
- **Decoupling**: the edge does not run any embedding model. The cloud does not depend on the edge model version.
- **Observability**: the edge pre-filter exposes its own CPU, memory, and throughput as Prometheus metrics.

## 4. Glossary

- **Vector**: the open-source data pipeline from Datadog. In this document it is not a vector database or an embedding model.
- **SLM**: Small Language Model, an edge model with at most 3B parameters.
- **VRL**: Vector Remap Language, the declarative transform language used by Vector.
- **RAG**: Retrieval-Augmented Generation.
