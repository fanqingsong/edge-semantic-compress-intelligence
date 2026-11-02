# 产品需求文档索引

本目录将 [系统需求文档](../requirements) 按服务拆成可分阶段实现和验收的 PRD。原需求编号在各文档中保留，便于追踪需求、设计和测试。代码位置见 [服务目录](../services/README.md)。

## PRD 列表

| 编号 | PRD | 服务 | 覆盖需求 | 主要依赖 |
|---|---|---|---|---|
| PRD-01 | [边缘日志采集与规则预过滤](prd-01-edge-ingestion-filtering.md) | [过滤](../services/edge/filtering.md) | E-01、E-02 | 无 |
| PRD-02 | [边缘 SLM 结构化提炼与实体校验](prd-02-edge-summarization.md) | [摘要](../services/edge/summarization.md) | E-03、E-04 | PRD-01 |
| PRD-03 | [边缘安全传输与弱网缓冲](prd-03-secure-transport.md) | [传输](../services/edge/transport.md) | E-05 | PRD-02；[cloud agent](../services/cloud/agent.md) |
| PRD-04 | [云端知识入库](prd-04-knowledge-ingestion.md) | [知识入库](../services/cloud/knowledge.md) | C-01 | 无；为 PRD-05 提供知识数据 |
| PRD-05 | [云端混合检索](prd-05-hybrid-retrieval.md) | [检索](../services/cloud/retrieval.md) | C-02 | PRD-04；边缘摘要契约 |
| PRD-06 | [云端 RAG 根因分析](prd-06-rag-analysis.md) | [RAG](../services/cloud/rag.md) | C-03 | PRD-05 |
| PRD-07 | [摘要质量反馈闭环](prd-07-feedback-loop.md) | [反馈](../services/cloud/feedback.md) | C-04 | PRD-02、PRD-06 |

edge agent 与 cloud agent 是组装进程，没有单独的 PRD。说明见 [edge agent](../services/edge/agent.md) 和 [cloud agent](../services/cloud/agent.md)。

## 建议实施顺序

1. **端到端 MVP**：PRD-01、PRD-03 的最小接入能力、PRD-04、PRD-05、PRD-06。按原技术方案，MVP 可用规则模拟边缘摘要，先验证云端链路。
2. **边缘智能提炼**：交付 PRD-02，并与 PRD-01、PRD-03 联调。
3. **质量改进闭环**：交付 PRD-07，建立评估、审核和回流流程。

PRD-03 的完整弱网可靠性、安全策略应在 MVP 中定义接口并明确未实现项，不能将模拟链路视为 E-05 已验收。

## 全局约束

- 边缘侧不部署 Embedding 模型；SLM 参数量不超过 3B；云端不依赖边缘模型版本。
- 边缘 SLM 输出必须受 JSON Schema 或 Grammar 约束，禁止自由文本作为结构化接口。
- 边缘预过滤引擎内存低于 50 MB；SLM 显存占用低于 2 GB；整机功耗低于 30 W。需在目标硬件上验证。
- 边缘预过滤引擎需暴露 Prometheus CPU、内存和吞吐量指标。
- 原始日志、摘要和检索结果的评测数据集及测量方法需在实施前定义；指标未定义测量条件时，不视为可复现验收。

## 待决策项

- **边缘组件与模型运行时**：技术方案默认 Fluent Bit，SLM 使用 llama.cpp；候选模型中包含 AWQ 与 GGUF 量化格式，需在目标硬件上确认兼容的模型格式和运行时。
- **传输协议**：在 MQTT v5 与 Kafka 中选择，并确定消息确认、重试、幂等、磁盘缓冲容量、断网时长及溢出处理。
- **云端存储与编排**：确定 Milvus 或 Elasticsearch，以及 LlamaIndex 或 LangChain。
- **精确 IP 过滤的降级行为**：无 target_ip 或无精确匹配时是否放宽过滤，以及放宽规则。
- **实体补全边界**：仅从原始日志提取，不得臆造；定义字段缺失且无法提取时的处理方式。
- **安全与数据治理**：定义原始日志脱敏、留存期限、证书轮换和 Prompt 建议上线前的审核要求。
- **指标评测口径**：定义无效日志、相关案例、可执行建议、摘要完整度的标注标准和评审流程。