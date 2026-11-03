The current implementation is written per service in the [service catalog](services/README.md). The rest of this page is the original technical design. It keeps the architecture diagrams and technology choices from that time and is not rearranged to match code packages.

The following is the final document, with the full content, architecture diagrams, and flowcharts combined. You can copy it into two separate `.md` files and use them as the standard input context for a coding agent.

📄 requirements.md for the edge log compression and cloud RAG system

Requirements: edge log compression and cloud RAG

Background
Build an AIOps log analysis system that combines structured compression on the edge with a decoupled RAG pipeline in the cloud. The edge pre-filters logs and distills them with an SLM. The cloud runs high-precision vector retrieval and root-cause reasoning. The result is a fault-diagnosis loop with low bandwidth, low latency, and high precision.

Functional requirements

2.1 Edge
ID   Module   Description   Acceptance criteria
E-01   Log collection   Collect raw logs from a configured file path or syslog   No log loss; resume from the last checkpoint

E-02   Rule pre-filter   L1 format check, L2 status-code filter, L3 keyword denylist, L4 rate suppression   Rules only, with no AI cost; at least 90% of invalid logs are blocked

E-03   SLM structured distillation   Send filtered log batches to a local SLM and emit a structured summary that matches a JSON Schema   100% valid JSON; per-batch latency under 2s

E-04   Entity validation fallback   Validate IP, port, and error code in the SLM output with regular expressions, and fill missing values   At least 99% of critical entity fields are complete

E-05   Secure transport   Send the structured event to the cloud over MQTT or Kafka   Topic ACL by MQTT username; local disk buffering with no data loss on a weak network

2.2 Cloud
ID   Module   Description   Acceptance criteria
C-01   Knowledge ingestion pipeline   Periodically clean operations documents and historical tickets, embed them with a cloud embedding model, and store the vectors   Incremental updates; document parsing accuracy of at least 95%

C-02   Hybrid retrieval   Exact filter on `target_ip` from the edge JSON, plus vector similarity search on `summary`   Top-5 recall of relevant cases of at least 85%

C-03   RAG reasoning   Assemble retrieved cases and the edge summary into a prompt, then call a large model for root-cause analysis and remediation suggestions   Response time under 10s; actionability score of at least 4/5

C-04   Feedback loop   Mark cases where the edge summary is insufficient, and generate prompt-optimization suggestions that flow back to the edge   At least 3 valid prompt-iteration suggestions per week

Non-functional requirements
Edge resource limits: pre-filter engine memory under 50 MB; SLM video memory under 2 GB; whole-device power under 30 W.
Deterministic output: the edge SLM must be constrained by a JSON Schema or grammar. Free-text generation is not allowed.
Decoupling: the edge does not run any embedding model. The cloud does not depend on the edge model version.
Observability: the edge pre-filter exposes its own CPU, memory, and throughput as Prometheus metrics.

Glossary
Vector: the open-source data pipeline from Datadog. In this document it is not a vector database or an embedding model.
SLM: Small Language Model, an edge model with at most 3B parameters.
VRL: Vector Remap Language, the declarative transform language used by Vector.
RAG: Retrieval-Augmented Generation.

🛠️ technical-design.md for the edge log compression and cloud RAG system

Technical design: edge log compression and cloud RAG

Architecture overview

1.1 System architecture
mermaid
graph TB
    subgraph Edge["🏭 Edge (resource constrained)"]
        A[Raw logs: files or syslog] --> B[Pre-filter: Fluent Bit / Vector]
        B -->|High-value log batches| C[SLM inference: llama.cpp + JSON Schema]
        C --> D[Entity validation fallback: regex backfill]
        D --> E[Secure transport: MQTT/Kafka]

        style B fill:#e1f5fe,stroke:#0288d1
        style C fill:#fff3e0,stroke:#f57c00
        style D fill:#f3e5f5,stroke:#7b1fa2
    end

    subgraph Cloud["☁️ Cloud (high-precision reasoning)"]
        F[Knowledge ingestion: Unstructured + bge-m3] --> G[(Vector store: Milvus / ES)]
        E -->|Structured JSON| H[RAG orchestration: LlamaIndex]
        G -->|Hybrid retrieval results| H
        H --> I[Root-cause LLM: Qwen2.5-72B / Claude]
        I --> J[Root-cause analysis report]
        J -.->|Prompt optimization suggestions| B

        style G fill:#e8f5e9,stroke:#388e3c
        style H fill:#fce4ec,stroke:#c2185b
        style I fill:#fff8e1,stroke:#ffa000
    end

    linkStyle default stroke:#546e7a,stroke-width:2px

1.2 Data-processing flow
mermaid
flowchart LR
    A[Raw logs] --> B{L1: format check}
    B -->|Invalid format| X1[Drop and count]
    B -->|Valid| C{L2: status-code filter}

    C -->|200/OK| X2[Drop and count]
    C -->|Not success| D{L3: keyword denylist}

    D -->|Heartbeat or health check| X3[Drop and count]
    D -->|Business log| E{L4: rate suppression}

    E -->|Repeats over threshold| X4[Keep first and last only]
    E -->|Normal rate| F[Batch aggregation max=10KB/1s]

    F --> G[SLM structured distillation, JSON Schema enforced]
    G --> H{Entity completeness check}

    H -->|Critical field missing| I[Regex backfill from the raw log]
    H -->|Complete| J[MessagePack serialization]
    I --> J

    J --> K[MQTT transport]
    K --> L[Cloud RAG pipeline]

    style X1 fill:#ffcdd2,stroke:#c62828
    style X2 fill:#ffcdd2,stroke:#c62828
    style X3 fill:#ffcdd2,stroke:#c62828
    style X4 fill:#fff9c4,stroke:#f9a825
    style G fill:#e3f2fd,stroke:#1565c0
    style L fill:#e8f5e9,stroke:#2e7d32

Edge technology choices and configuration

2.1 Pre-filter engine (Fluent Bit recommended by default)
Why: written in C, 5–10 MB of memory, a mature ARM ecosystem, and reliable offline buffering.
Alternative: on a Jetson or RK3588 with complex rules, Vector (Rust, strong VRL) is an option.
Configuration requirements:
    Enable `storage.type filesystem` disk buffering
    Output batch size `batch.max_size=10KB`, flush interval = 1s
    Use only filter, grep, and throttle plugins. Do not load any AI plugin

2.2 SLM inference service
Base model: Qwen2.5-1.5B-Instruct-AWQ or Llama-3.2-3B-Q4_K_M
Inference framework: llama.cpp in server mode
Required startup arguments:
    bash
    --json-schema '{"type":"object","properties":{"timestamp":{"type":"string"},"service":{"type":"string"},"target_ip":{"type":"string"},"error_code":{"type":"string"},"summary":{"type":"string"}},"required":["timestamp","service","summary"]}'
    --ctx-size 2048 --threads 4 --gpu-layers 99
    API: `POST /v1/chat/completions`. The request body must include `response_format: {"type": "json_object"}`

2.3 Entity-validation fallback script
Language: Python 3.10+ or Lua embedded in Fluent Bit
Logic: extract `(d{1,3}.){3}d{1,3}` (IP), `bd{4,5}b` (port), and `ERR-d+` (error code) with regular expressions. Backfill a missing field from the raw log.

Cloud technology choices and configuration

3.1 Knowledge ingestion
Document parsing: Unstructured / MarkItDown
Embedding model: bge-m3 (1024 dimensions; Chinese and English; dense and sparse retrieval)
Vector database: Milvus 2.x or Elasticsearch 8.x or newer, chosen from the existing infrastructure

3.2 RAG pipeline
Orchestration framework: LlamaIndex (recommended) or LangChain
Retrieval strategy: hybrid search = metadata filter (`target_ip==xxx`) + vector similarity (`summary`, `top_k=5`)
Inference model: Qwen2.5-72B-Instruct (deployed with vLLM) or the Claude 3.5 Sonnet API
Prompt template: must contain the three sections `<edge_summary>`, `<retrieved_cases>`, and `<analysis_instructions>`

Communication protocol
Transport protocol: MQTT v5 (preferred on a weak network) or Kafka (preferred for high throughput)
Serialization: MessagePack (about 30% smaller than JSON, and about 5 times faster to parse)
Security: topic-level ACLs by MQTT username

Implementation phases
Phase   Duration   Deliverable   Verification
Phase 1   2 weeks   Pre-filter plus the cloud RAG path (the SLM is simulated with rules)   Cloud RAG recall accuracy of at least 80%

Phase 2   3 weeks   Edge SLM online, plus entity validation   100% valid JSON; summary quality passes human review

Phase 3   Ongoing   Feedback loop and automatic prompt iteration   Summary-information completeness improves by at least 5% per month

Coding agent instructions
⚠️ Key notes for the agent
When implementing the pre-filter, do not import any embedding library such as sentence-transformers or openai-embeddings.
The llama.cpp startup command must include `--json-schema`. Do not omit it.
Cloud RAG retrieval must use both the metadata filter and vector search. Vector search alone is not enough.
Every configuration file needs comments that state the expected block rate and the engineering purpose of each filter layer.
Implement the Fluent Bit option first. Switch to Vector only when the user explicitly asks for it.
Generated code must stay consistent with the architecture diagram and the flowchart in this document. Do not add or remove core nodes on your own.
The diagrams are mandatory design constraints, not illustrations. If the diagram and the text conflict, follow the written description in this document and report the conflict immediately.

💡 Delivery and usage checklist
Step   Action   Purpose
1   Save the first block as requirements.md   Define the business boundary and non-functional constraints

2   Save the second block as technical-design.md   Provide the full technical blueprint, including diagrams

3   Upload requirements.md to the coding agent first   Establish global context and avoid over-design

4   Then upload technical-design.md and assign the task   Trigger implementation phase by phase

5   After each phase, manually check consistency with the diagrams   Confirm the agent has not drifted from the architecture

Note: both documents already include every point discussed earlier (the Fluent Bit versus Vector conclusion, the four pre-filter layers, the forced SLM JSON Schema, the cloud hybrid-retrieval strategy, and the feedback loop). No extra history needs to be attached.
