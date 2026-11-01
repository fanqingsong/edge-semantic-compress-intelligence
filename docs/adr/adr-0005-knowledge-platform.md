# ADR-0005：云端知识入库与向量存储

- 状态：已采纳（MVP 默认：bge-m3 + Milvus + MarkItDown）
- 日期：2026-11-01
- 关联 PRD：PRD-04

## 背景

云端需要持续解析运维文档和历史工单，向量化并支持增量更新，为混合检索提供数据。技术方案列出多个解析器和向量存储候选。

## 当前架构约束

- 文档清洗、解析和 Embedding 均在云端执行。
- 知识数据支持增量更新，并保留来源追溯信息。
- 技术方案推荐 bge-m3；文档解析候选为 Unstructured 或 MarkItDown；向量存储候选为 Milvus 2.x 或 Elasticsearch 8.x+。
- 原始 Markdown/TXT 通过确定性字段解析；PDF、DOCX、PPTX、HTML 使用 MarkItDown 转为 Markdown，再提取案例字段。
- 文档必须显式包含 `Summary` 和 `Resolution` 字段；不满足结构的文档报错，不用模型猜测或生成知识事实。

## 决策

- 按 MVP 默认技术栈使用 bge-m3 Embedding 服务和 Milvus 向量存储；保留 `TextEmbedder`、`VectorIndex` 适配边界，允许后续替换。
- `knowledge-ingest` CLI 可解析 JSONL、Markdown、TXT 及 MarkItDown 支持的 PDF、DOCX、PPTX、HTML，并增量写入 Milvus。
- 当前代码提供 bge-m3 HTTP 客户端、Milvus VectorIndex 适配器和集合初始化函数；集合初始化会创建缺失集合，并拒绝必需字段或向量维度不匹配的已有集合。
- Milvus 集合需要包含 `case_id`（主键）、`summary`、`resolution`、`source`、`target_ip`、`version` 和 `embedding` 向量字段；默认向量维度为 1024，需与实际模型输出一致。
- `embedding` 使用 COSINE metric 和 AUTOINDEX；集合初始化不启动 Milvus 服务，也不替代生产环境备份/迁移流程。
- 已通过本地 Milvus 2.5.4 集成测试验证集合创建、向量 upsert、`target_ip` 精确过滤检索和 source 级删除。

## 后续配置

- 扩充原始文档格式覆盖和解析准确率评测集；当前不提供 OCR，也不支持没有显式案例字段的任意散文自动语义拆分。
- 确认实际 bge-m3 服务部署、向量维度、索引参数、集合创建和升级迁移方式。
- 定义增量更新、重复文档识别、删除传播、失败重试和全量重建策略。
- 定义文档解析准确率不低于 95% 的评测集、抽样方法与标注标准。

## 影响

- PRD-05 的过滤字段和召回能力依赖这里确定的元数据结构与索引能力。
- 更换 Embedding 模型或向量存储需要评估重算向量、索引迁移和检索质量回归。

## 候选方案

- Milvus：专用向量数据库方向。
- Elasticsearch：可复用现有搜索基础设施并承载元数据检索。