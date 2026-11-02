# 架构决策记录

本目录记录影响系统边界、技术选型和跨组件契约的架构决策。业务目标与验收标准以 [PRD 索引](../prds/README.md) 和各 PRD 为准；实现位置以 [服务目录](../services/README.md) 为准；技术背景来源于 [技术方案](../technology)。

## ADR 列表

| 编号 | 决策 | 状态 | 服务 | 关联 PRD |
|---|---|---|---|---|
| ADR-0001 | [边缘与云端职责解耦](adr-0001-edge-cloud-boundary.md) | 已采纳 | [全部服务](../services/README.md) | PRD-01 至 PRD-07 |
| ADR-0002 | [边缘采集与预过滤引擎](adr-0002-edge-collector.md) | 已采纳（默认方案） | [过滤](../services/edge/filtering.md) | PRD-01 |
| ADR-0003 | [边缘 SLM 本地推理与受约束输出](adr-0003-edge-slm-runtime.md) | 已采纳（约束）；模型待定 | [摘要](../services/edge/summarization.md) | PRD-02 |
| ADR-0004 | [边缘到云端的安全消息传输](adr-0004-secure-transport.md) | 已采纳（MVP：MQTT） | [传输](../services/edge/transport.md) | PRD-03 |
| ADR-0005 | [云端知识入库与向量存储](adr-0005-knowledge-platform.md) | 已采纳（Milvus/bge-m3/MarkItDown MVP） | [知识入库](../services/cloud/knowledge.md) | PRD-04 |
| ADR-0006 | [元数据过滤与向量检索组合](adr-0006-hybrid-retrieval.md) | 已采纳（策略）；回退待定 | [检索](../services/cloud/retrieval.md) | PRD-05 |
| ADR-0007 | [RAG 编排与推理模型](adr-0007-rag-platform.md) | 待决策 | [RAG](../services/cloud/rag.md) | PRD-06 |
| ADR-0008 | [摘要质量反馈与 Prompt 治理](adr-0008-feedback-governance.md) | 已采纳（人工审核，不自动分发） | [反馈](../services/cloud/feedback.md) | PRD-07 |
| ADR-0009 | [边缘事件 Schema 与数据最小化](adr-0009-edge-event-contract.md) | 已采纳（MVP） | [shared](../services/shared.md) | PRD-02、PRD-03、PRD-05 |
| ADR-0010 | [按服务粒度管理代码与文档](adr-0010-service-granularity.md) | 已采纳 | [全部服务](../services/README.md) | PRD-01 至 PRD-07 |

## 状态说明

- **已采纳**：架构方向或约束已由需求/技术方案明确，可据此实现。
- **待决策**：存在候选项或关键运行参数未定；开始对应生产实现前需要补充决策。
- 标为“已采纳（默认方案）”表示默认采用文档推荐，切换方案需要明确提出并更新 ADR。

## 决策规则

每项 ADR 描述背景、决策、替代方案、影响和待解决问题。待决策 ADR 不代表所有候选方案都已验证；选型后应更新状态、依据、日期及影响，不覆盖历史结论。