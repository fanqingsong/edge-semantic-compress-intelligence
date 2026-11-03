# RAG

Code: [`libs/cloud/src/cloud/rag`](../../../libs/cloud/src/cloud/rag)

Related: [PRD-06](../../prds/prd-06-rag-analysis.md), [ADR-0007](../../adr/adr-0007-rag-platform.md)

## Responsibilities

Produce a root-cause analysis from one `EdgeEvent` and the cases returned by [retrieval](retrieval.md). This service does not connect to MQTT and does not write the knowledge base.

The prompt is fixed as three sections: `<edge_summary>`, `<retrieved_cases>`, and `<analysis_instructions>`. Summaries and cases are escaped as untrusted data and cannot be treated as instructions.

The analysis model is the OpenAI-compatible API at `SILICONFLOW_BASE_URL`, using `CLOUD_ANALYSIS_MODEL` (`Qwen/Qwen2.5-72B-Instruct`) and `SILICONFLOW_API_KEY`. The orchestration framework is still an open choice under ADR-0007. The current runtime path does not use LlamaIndex or LangChain.

The [cloud agent](agent.md) calls this service and writes the result to `analyses.sqlite3`.
