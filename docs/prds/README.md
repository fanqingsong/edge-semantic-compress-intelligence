# Product requirements index

This directory splits the [system requirements](../requirements) into PRDs that can be implemented and accepted in stages. Each document keeps the original requirement IDs so requirements, design, and tests stay traceable. Code locations are in the [service catalog](../services/README.md).

## PRD list

| ID | PRD | Service | Requirements | Main dependencies |
|---|---|---|---|---|
| PRD-01 | [Edge log collection and rule pre-filtering](prd-01-edge-ingestion-filtering.md) | [Filtering](../services/edge/filtering.md) | E-01, E-02 | None |
| PRD-02 | [Edge SLM structured distillation and entity validation](prd-02-edge-summarization.md) | [Summarization](../services/edge/summarization.md) | E-03, E-04 | PRD-01 |
| PRD-03 | [Edge secure transport and weak-network buffering](prd-03-secure-transport.md) | [Transport](../services/edge/transport.md) | E-05 | PRD-02; [cloud agent](../services/cloud/agent.md) |
| PRD-04 | [Cloud knowledge ingestion](prd-04-knowledge-ingestion.md) | [Knowledge ingestion](../services/cloud/knowledge.md) | C-01 | None; supplies knowledge data for PRD-05 |
| PRD-05 | [Cloud hybrid retrieval](prd-05-hybrid-retrieval.md) | [Retrieval](../services/cloud/retrieval.md) | C-02 | PRD-04; edge summary contract |
| PRD-06 | [Cloud RAG root-cause analysis](prd-06-rag-analysis.md) | [RAG](../services/cloud/rag.md) | C-03 | PRD-05 |
| PRD-07 | [Summary-quality feedback loop](prd-07-feedback-loop.md) | removed | C-04 | PRD-02, PRD-06 |

The edge agent and the cloud agent are assembly processes and do not have their own PRDs. See the [edge agent](../services/edge/agent.md) and the [cloud agent](../services/cloud/agent.md).

## Suggested implementation order

1. **End-to-end MVP**: PRD-01, the minimum ingress from PRD-03, PRD-04, PRD-05, and PRD-06. Following the original technical design, the MVP may simulate the edge summary with rules and validate the cloud path first.
2. **Edge intelligent distillation**: deliver PRD-02 and integrate it with PRD-01 and PRD-03.
3. **Quality-improvement loop**: deliver PRD-07 and establish evaluation, review, and feedback.

The full weak-network reliability and security policy of PRD-03 should have their interfaces defined in the MVP, with unimplemented items called out. A simulated path does not count as acceptance of E-05.

## Global constraints

- The edge does not run an embedding model. The SLM has at most 3B parameters. The cloud does not depend on the edge model version.
- Edge SLM output must be constrained by a JSON Schema or grammar. Free text is not a structured interface.
- Edge pre-filter memory is under 50 MB. SLM video memory is under 2 GB. Whole-device power is under 30 W. These limits must be verified on the target hardware.
- The edge pre-filter exposes Prometheus metrics for CPU, memory, and throughput.
- Evaluation datasets and measurement methods for raw logs, summaries, and retrieval results must be defined before implementation. A metric without a defined measurement condition is not a reproducible acceptance criterion.

## Open decisions

- **Edge components and model runtime**: the technical design defaults to Fluent Bit, and the SLM uses llama.cpp. Candidate models include AWQ and GGUF quantization. The compatible model format and runtime must be confirmed on the target hardware.
- **Transport protocol**: choose MQTT v5 or Kafka, and define acknowledgement, retry, idempotency, disk-buffer capacity, offline duration, and overflow behavior.
- **Cloud storage and orchestration**: choose Milvus or Elasticsearch, and LlamaIndex or LangChain.
- **Fallback for exact IP filtering**: decide whether to relax the filter when `target_ip` is missing or there is no exact match, and define the relaxation rule.
- **Entity backfill boundary**: values may be extracted only from the raw log and must not be invented. Define the behavior when a field is missing and cannot be extracted.
- **Security and data governance**: define raw-log redaction, retention, and the review required before a prompt suggestion goes live.
- **Metric definitions**: define labeling standards and review procedures for invalid logs, relevant cases, actionable suggestions, and summary completeness.
