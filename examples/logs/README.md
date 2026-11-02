# Fluent Bit 输入目录

将符合 JSON Lines 输入约定的 `.jsonl` 文件放在此目录，Fluent Bit 会读取并转发给 [edge agent](../../docs/services/edge/agent.md)。规则过滤见 [过滤服务](../../docs/services/edge/filtering.md)。日志样例默认不提交，以免把真实运维数据写入版本库。