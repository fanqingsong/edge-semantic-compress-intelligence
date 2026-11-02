# 知识入库

代码：[`services/cloud/knowledge`](../../../src/edge_semantic_compress_intelligence/services/cloud/knowledge)

进程：`knowledge-ingest`。Compose profile `tools` 中的服务名是 `knowledge-ingest`。它不在在线故障分析链路上常驻。

关联：[PRD-04](../../prds/prd-04-knowledge-ingestion.md)、[ADR-0005](../../adr/adr-0005-knowledge-platform.md)

## 职责

读取运维文档或历史案例，解析成带 `target_ip` 的案例，调用[检索](retrieval.md)服务的向量写入接口，写入 Milvus 集合 `ops_cases`。向量维度为 1024。

- 支持 JSON Lines，以及 Markdown、TXT、PDF、DOCX、PPTX、HTML。后一类经 MarkItDown 转换。
- 文档必须显式包含 `Summary` 和 `Resolution`。字段不足时失败，不用模型补写事实。
- Embedding 使用 bge-m3 HTTP，或检索服务提供的确定性 mock。
- 入库使用的 IP 字段与在线检索的过滤字段相同。

样例见 [examples/knowledge](../../../examples/knowledge/README.md)。导入命令见 [本地开发](../../local-development.md)。
