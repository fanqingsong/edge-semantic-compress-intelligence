# 传输

代码：[`services/edge/transport`](../../../src/edge_semantic_compress_intelligence/services/edge/transport)

关联：[PRD-03](../../prds/prd-03-secure-transport.md)、[ADR-0004](../../adr/adr-0004-secure-transport.md)

## 职责

把 `EdgeEvent` 编码为 MessagePack，以 QoS 1 发到默认主题 `edge/events`。发出前写入 SQLite outbox，收到 broker 的发布确认后才删除。该确认只表示 broker 已接收，不表示云端业务已完成。

断线期间事件留在本地，连接恢复后补传。outbox 默认上限 100 MiB。达到上限时拒绝新事件，不覆盖旧记录。[edge agent](agent.md) 把这种情况返回为 HTTP 507。

本服务不解析日志，也不调用摘要模型。mTLS 与 Topic ACL 由 Mosquitto 执行：`edge-agent` 证书只可写 `edge/events`。
