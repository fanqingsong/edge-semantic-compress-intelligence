# shared

代码：[`shared`](../../src/edge_semantic_compress_intelligence/shared)

`shared` 保存跨服务契约，不包含过滤、摘要、检索或分析逻辑。

## 职责

- `EdgeEvent` 是边缘到云端的唯一业务契约，schema `1.0` 的机器可读定义在 [schemas/edge-event-v1.schema.json](../../schemas/edge-event-v1.schema.json)。
- MessagePack 编解码供传输服务和 cloud agent 使用。JSON 只约束模型输出。
- MQTT 客户端工厂和 mTLS 配置供 edge agent 与 cloud agent 使用。

## 契约

- 必填：`event_id`（UUID）、`schema_version`、带时区的 ISO 8601 `timestamp`、非空 `service`、非空 `summary`。
- 可选：`target_ip`、`target_port`、`error_code`。IP 必须可解析；端口为 1–65535。
- 未知字段拒绝。事件不含原始日志。

决策见 [ADR-0009](../adr/adr-0009-edge-event-contract.md)。摘要服务产出该契约，传输服务投递它，检索和 RAG 消费它。
