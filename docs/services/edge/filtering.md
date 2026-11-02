# 过滤

代码：[`services/edge/filtering`](../../../src/edge_semantic_compress_intelligence/services/edge/filtering)

关联：[PRD-01](../../prds/prd-01-edge-ingestion-filtering.md)、[ADR-0002](../../adr/adr-0002-edge-collector.md)

## 职责

对一批日志做纯规则过滤，不调用模型，也不做 Embedding。通过的记录按服务交给[摘要](summarization.md)。

规则顺序固定：

1. L1 格式校验，丢弃原因 `invalid_format`。
2. L2 成功状态，丢弃 `200` 或 `ok`，原因 `success_status`。
3. L3 关键字黑名单，丢弃心跳或健康检查，原因 `blacklisted_keyword`。
4. L4 频率抑制。同一服务、同一消息超过阈值时只保留首尾，原因 `frequency_suppressed`。

采集不在这个包里。Fluent Bit 读取文件并在 UDP `5514` 接收 Syslog，归一化后把日志批次交给 [edge agent](agent.md)。配置在 [`deploy/fluent-bit`](../../../deploy/fluent-bit)。
