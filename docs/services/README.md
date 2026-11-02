# 服务目录

实现按服务分包。每个服务只拥有自己的代码；进程入口负责组装，不把其他服务的实现放进同一个包。跨边缘和云端的契约在 [`shared`](shared.md)。这条粒度规则见 [ADR-0010](../adr/adr-0010-service-granularity.md)。

需求与验收仍以 [PRD 索引](../prds/README.md) 为准，选型与约束以 [ADR 索引](../adr/README.md) 为准。

## 边缘

| 服务 | 代码 | 运行方式 | 说明 |
|---|---|---|---|
| 过滤 | [`services/edge/filtering`](../../src/edge_semantic_compress_intelligence/services/edge/filtering) | 由 edge agent 调用 | [过滤](edge/filtering.md) |
| 摘要 | [`services/edge/summarization`](../../src/edge_semantic_compress_intelligence/services/edge/summarization) | 由 edge agent 调用 | [摘要](edge/summarization.md) |
| 传输 | [`services/edge/transport`](../../src/edge_semantic_compress_intelligence/services/edge/transport) | 由 edge agent 调用 | [传输](edge/transport.md) |
| edge agent | [`services/edge/agent`](../../src/edge_semantic_compress_intelligence/services/edge/agent) | 进程 `edge-log-agent` | [edge agent](edge/agent.md) |

Fluent Bit 负责采集，配置在 [`deploy/fluent-bit`](../../deploy/fluent-bit)，不是这四个 Python 服务之一。

## 云端

| 服务 | 代码 | 运行方式 | 说明 |
|---|---|---|---|
| 知识入库 | [`services/cloud/knowledge`](../../src/edge_semantic_compress_intelligence/services/cloud/knowledge) | 进程 `knowledge-ingest` | [知识入库](cloud/knowledge.md) |
| 检索 | [`services/cloud/retrieval`](../../src/edge_semantic_compress_intelligence/services/cloud/retrieval) | 由 knowledge 与 cloud agent 调用 | [检索](cloud/retrieval.md) |
| RAG | [`services/cloud/rag`](../../src/edge_semantic_compress_intelligence/services/cloud/rag) | 由 cloud agent 调用 | [RAG](cloud/rag.md) |
| 反馈 | [`services/cloud/feedback`](../../src/edge_semantic_compress_intelligence/services/cloud/feedback) | 进程 `prompt-feedback`；在线观察由 cloud agent 调用 | [反馈](cloud/feedback.md) |
| cloud agent | [`services/cloud/agent`](../../src/edge_semantic_compress_intelligence/services/cloud/agent) | 进程 `cloud-rag-agent` | [cloud agent](cloud/agent.md) |

## 依赖方向

- `shared` 不依赖任何服务。
- 摘要读取过滤产出的日志记录。传输不依赖过滤或摘要。
- edge agent 组装过滤、摘要和传输。
- 知识入库只依赖检索的向量写入接口。
- RAG 使用检索产出的 `RetrievedCase`。
- 反馈读取 RAG 的分析结果。
- cloud agent 组装检索、RAG 和反馈观察，并负责 MQTT 消费。
