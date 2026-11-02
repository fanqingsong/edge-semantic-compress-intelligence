# Fluent Bit 输入目录

将符合 JSON Lines 输入约定的 `.jsonl` 文件放在此目录，Fluent Bit 会读取并转发给 [edge agent](../../docs/services/edge/agent.md)。规则过滤见 [过滤服务](../../docs/services/edge/filtering.md)。真实运维日志不要提交。合成样例 [`payments-incident.jsonl`](payments-incident.jsonl) 是例外，用于本地采集测试，内容对应知识库案例 `CASE-2026-001`。