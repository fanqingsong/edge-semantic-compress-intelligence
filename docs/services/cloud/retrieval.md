# 检索

代码：[`services/cloud/retrieval`](../../../src/edge_semantic_compress_intelligence/services/cloud/retrieval)

关联：[PRD-05](../../prds/prd-05-hybrid-retrieval.md)、[ADR-0006](../../adr/adr-0006-hybrid-retrieval.md)

## 职责

提供混合检索和向量库适配。本服务没有独立进程。[知识入库](knowledge.md)用它写入，[cloud agent](agent.md)用它按事件检索。

检索结果类型 `RetrievedCase` 定义在这里。[RAG](rag.md)依赖该类型，检索不依赖 RAG。

在线检索规则：

- 同时使用 `target_ip` 精确过滤和 `summary` 向量相似度。
- `top_k` 固定为 5。
- 缺少 `target_ip`，或没有精确 IP 匹配时，返回空案例集，不退化为纯向量搜索。
- 向量库返回之后再次比对 IP，避免索引配置错误造成跨主机召回。

Milvus 集合适配、bge-m3 HTTP 客户端和确定性 mock embedder 都属于检索服务。
