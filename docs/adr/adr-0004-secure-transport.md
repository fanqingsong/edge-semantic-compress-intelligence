# ADR-0004：边缘到云端的安全消息传输

- 状态：已采纳（MVP：MQTT v5 + MessagePack + SQLite outbox）
- 日期：2026-11-01
- 关联 PRD：PRD-03
- 代码：[传输](../services/edge/transport.md)，云端消费在 [cloud agent](../services/cloud/agent.md)

## 背景

边缘需要通过不稳定网络发送结构化摘要。系统要求 mTLS 和本地磁盘缓冲；技术方案提出 MQTT v5 与 Kafka 两个候选，并指定 MessagePack 序列化。

## 当前约束

- 传输必须使用 mTLS 双向认证。
- 结构化消息使用 MessagePack 在线路上传输；模型生成的 JSON 与线路编码边界需要明确。
- 弱网时在本地磁盘缓冲，恢复连接后补传。
- 必须具备可验证的消息确认、重试和幂等处理机制。

## 决策

- MVP 采用 MQTT v5，使用 QoS 1 发布结构化事件并以 MessagePack 编码。
- 使用 SQLite 持久 outbox；默认容量上限 100 MiB，可配置。达到上限时拒绝新入队并显式报错，不静默丢弃或覆盖旧事件。
- 仅在收到 broker 发布确认后删除本地 outbox 记录。此确认不代表云端业务已处理；云端仍需按 `event_id` 幂等消费。
- 云端消费者启用 MQTT 手动 ACK：业务处理成功并持久记录 `event_id` 后才 ACK；相同 ID/相同内容的重复消息直接 ACK，不重复调用处理器；相同 ID/不同内容不 ACK。
- 该模式提供至少一次投递，不承诺 exactly-once；业务处理器需要按 `event_id` 幂等，因为进程可能在业务成功后、去重记录落盘前退出。
- MQTT broker 监听 TLS 8883，强制验证 CA 签发的客户端证书，并以证书 CN 映射 ACL 身份。
- ACL 仅允许 `edge-agent` 向 `edge/events` 发布、`cloud-agent` 从该主题订阅；独立 `healthcheck` 身份只读 `$SYS/broker/uptime`。
- Edge/Cloud 客户端和 Broker 都配置 mTLS；本地开发使用 `scripts/generate-dev-mqtt-certs.sh` 生成的自签名开发证书，证书目录被 Git 忽略。
- 生产必须使用组织 CA 和独立设备证书，配置轮换、吊销和受控密钥存储；不得复用开发 CA/密钥。

## 后续配置

- 定义目标设备的磁盘配额、最大离线时长和 outbox 满载告警/处置。
- 为生产 MQTT broker 配置组织 CA、证书轮换/吊销和云端消费确认策略。
- 评估本地 outbox 的静态数据加密需求；当前仅限制数据库文件权限，不提供磁盘加密。
- 若未来已有 Kafka 基础设施或吞吐量需求改变，再评估新增 Kafka transport adapter。

## 影响

- 协议选择会影响边缘资源占用、云端接入方式、部署复杂度和可实现的交付语义。
- 生产实现前需要端到端断网、进程重启、重复投递和证书失效测试。

## 替代方案

- MQTT v5：更贴近弱网和边缘设备场景。
- Kafka：更适合已有 Kafka 基础设施且吞吐量要求较高的场景。