# RAG

代码：[`services/cloud/rag`](../../../src/edge_semantic_compress_intelligence/services/cloud/rag)

关联：[PRD-06](../../prds/prd-06-rag-analysis.md)、[ADR-0007](../../adr/adr-0007-rag-platform.md)

## 职责

根据一个 `EdgeEvent` 和[检索](retrieval.md)返回的案例生成根因分析。本服务不连接 MQTT，也不写知识库。

Prompt 固定为三段：`<edge_summary>`、`<retrieved_cases>`、`<analysis_instructions>`。摘要和案例按不可信数据转义，不能被当成指令。

分析模型可以是确定性 mock，或 OpenAI 兼容接口。编排框架仍按 ADR-0007 待选型；当前运行路径不使用 LlamaIndex 或 LangChain。

[cloud agent](agent.md)调用本服务，并把结果写入 `analyses.sqlite3`。
