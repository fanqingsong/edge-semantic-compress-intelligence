# edge agent

代码：[`services/edge/agent`](../../../src/edge_semantic_compress_intelligence/services/edge/agent)

进程：`edge-log-agent`。Compose 服务名是 `edge-agent`，监听 `8090`。

## 职责

这是边缘侧唯一常驻进程。它不实现过滤、摘要或传输规则，只按顺序调用：

1. [过滤](filtering.md)
2. [摘要](summarization.md)，按服务各生成一个事件
3. [传输](transport.md)

Fluent Bit 把日志批次 `POST` 到 `/v1/logs`。正文是 UTF-8 日志行，默认上限 1 MiB。`GET /healthz` 只表示进程存活，不表示 outbox 已清空或云端已处理。

本地启动和证书见 [本地开发](../../local-development.md)。
