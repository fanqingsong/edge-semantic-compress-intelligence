# 摘要

代码：[`services/edge/summarization`](../../../src/edge_semantic_compress_intelligence/services/edge/summarization)

关联：[PRD-02](../../prds/prd-02-edge-summarization.md)、[ADR-0003](../../adr/adr-0003-edge-slm-runtime.md)

## 职责

把同一服务的过滤结果提炼成一个 [`EdgeEvent`](../shared.md)。本服务不部署 Embedding，也不负责发送。

- `EDGE_SUMMARIZER=mock` 使用确定性 mock，供无模型联调。
- `EDGE_SUMMARIZER=llama_cpp` 调用 llama.cpp server。请求必须带 JSON Schema，输出不是自由文本。
- 实体校验只从本批原始日志回补 IP、端口和错误码。日志里没有的值保持空，不臆造。
- 端口只从显式端口字段或带端口标签的文本提取。

摘要服务依赖过滤服务给出的日志记录。事件校验通过后交给[传输](transport.md)。
