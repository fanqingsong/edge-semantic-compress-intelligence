# cloud agent

代码：[`services/cloud/agent`](../../../src/edge_semantic_compress_intelligence/services/cloud/agent)

进程：`cloud-rag-agent`。Compose 服务名是 `cloud-agent`。

## 职责

这是云端在线链路的常驻进程。它订阅 `edge/events`，然后调用：

1. [检索](retrieval.md)
2. [RAG](rag.md)，结果写入 `analyses.sqlite3`
3. [反馈](feedback.md)的观察接口，建议写入 `feedback.sqlite3`

消费记录在 `processed.sqlite3`。处理成功且 `event_id` 与载荷哈希落盘后才手动 ACK。相同 ID、相同载荷的重复消息直接 ACK，不再次调用处理器。相同 ID、不同载荷不 ACK。解码失败或处理失败也不 ACK。

`cloud-agent` 证书只可订阅 `edge/events`。知识入库和反馈审核不在这个进程里。
