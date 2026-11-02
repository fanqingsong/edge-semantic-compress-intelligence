当前实现按服务写在 [服务目录](services/README.md)。下文是原始技术方案，保留当时的架构图和选型，不按代码包重排。

以下是整合了完整内容、架构图与流程图的最终版文档。您可以直接复制保存为两个独立的 .md 文件，作为 Coding Agent 的标准化输入上下文。

📄 边缘日志智能压缩与云端RAG系统需求文档.md

边缘日志智能压缩与云端RAG系统需求文档

项目背景
构建一套“边缘结构化压缩 + 云端解耦 RAG”的 AIOps 日志分析系统。边缘侧负责日志预过滤与 SLM 结构化提炼，云端负责高精度向量检索与根因推理，实现低带宽、低延迟、高精度的故障诊断闭环。

核心功能需求

2.1 边缘侧
ID   功能模块   描述   验收标准
E-01   日志采集   支持从指定文件路径/Syslog 采集原始日志   不丢日志，支持断点续传

E-02   规则预过滤   L1格式校验、L2状态码过滤、L3关键字黑名单、L4频率抑制   纯规则执行，零AI开销；无效日志拦截率≥90%

E-03   SLM结构化提炼   将过滤后日志批量发送给本地SLM，输出符合JSON Schema的结构化摘要   JSON合法率100%；单批处理延迟<2s

E-04   实体校验兜底   对SLM输出进行IP/端口/错误码正则校验，缺失时自动补全   关键实体字段完整率≥99%

E-05   安全传输   通过MQTT/Kafka将结构化JSON加密传输至云端   支持mTLS认证；弱网下本地磁盘缓冲不丢数据

2.2 云端侧
ID   功能模块   描述   验收标准
C-01   知识入库管道   定期清洗运维文档/历史工单，用云端Embedding模型向量化入库   支持增量更新；文档解析准确率≥95%

C-02   混合检索   基于边缘JSON中的target_ip做精确过滤 + summary做向量相似度搜索   Top-5召回相关案例命中率≥85%

C-03   RAG推理   将召回案例+边缘摘要组装Prompt，调用大模型生成根因分析与修复建议   响应时间<10s；建议可执行性评分≥4/5

C-04   反馈闭环   标记边缘摘要缺失案例，自动生成Prompt优化建议回流边缘   每周产出≥3条有效Prompt迭代建议

非功能性需求
边缘资源约束：预过滤引擎内存 < 50MB；SLM显存占用 < 2GB；整机功耗 < 30W。
确定性输出：边缘SLM必须启用 JSON Schema / Grammar 强制约束，禁止自由文本生成。
解耦原则：边缘侧不部署任何 Embedding 模型；云端不依赖边缘侧模型版本。
可观测性：边缘预过滤引擎自身CPU/内存/吞吐量需暴露 Prometheus 指标。

术语表
Vector：指 Datadog 开源的数据管道工具，非向量数据库或嵌入模型。
SLM：Small Language Model，参数量≤3B的边缘专用小模型。
VRL：Vector Remap Language，Vector 的声明式转换语言。
RAG：Retrieval-Augmented Generation，检索增强生成。

🛠️ 边缘日志智能压缩与云端RAG系统技术设计方案.md

边缘日志智能压缩与云端RAG系统技术设计方案

架构总览

1.1 系统架构图
mermaid
graph TB
    subgraph Edge["🏭 边缘侧 (资源受限)"]
        A[原始日志源文件/Syslog] --> B[预过滤引擎Fluent Bit / Vector]
        B -->|高价值日志批次| C[SLM推理服务llama.cpp + JSON Schema]
        C --> D[实体校验兜底正则补全]
        D --> E[安全传输层MQTT/Kafka + mTLS]

        style B fill:#e1f5fe,stroke:#0288d1
        style C fill:#fff3e0,stroke:#f57c00
        style D fill:#f3e5f5,stroke:#7b1fa2
    end

    subgraph Cloud["☁️ 云端侧 (高精度推理)"]
        F[知识入库管道Unstructured + bge-m3] --> G[(向量数据库Milvus / ES)]
        E -->|结构化JSON| H[RAG编排引擎LlamaIndex]
        G -->|混合检索结果| H
        H --> I[根因推理LLMQwen2.5-72B / Claude]
        I --> J[根因分析报告]
        J -.->|Prompt优化建议| B

        style G fill:#e8f5e9,stroke:#388e3c
        style H fill:#fce4ec,stroke:#c2185b
        style I fill:#fff8e1,stroke:#ffa000
    end

    linkStyle default stroke:#546e7a,stroke-width:2px

1.2 数据处理流程图
mermaid
flowchart LR
    A[原始日志] --> B{L1: 格式校验}
    B -->|非法格式| X1[丢弃+计数]
    B -->|合法| C{L2: 状态码过滤}

    C -->|200/OK| X2[丢弃+计数]
    C -->|非成功| D{L3: 关键字黑名单}

    D -->|心跳/健康检查| X3[丢弃+计数]
    D -->|业务日志| E{L4: 频率抑制}

    E -->|重复超阈值| X4[仅保留首尾]
    E -->|正常频次| F[批量聚合max=10KB/1s]

    F --> G[SLM结构化提炼JSON Schema强制]
    G --> H{实体完整性校验}

    H -->|缺失关键字段| I[正则回补原始日志]
    H -->|完整| J[MessagePack序列化]
    I --> J

    J --> K[mTLS加密传输]
    K --> L[云端RAG Pipeline]

    style X1 fill:#ffcdd2,stroke:#c62828
    style X2 fill:#ffcdd2,stroke:#c62828
    style X3 fill:#ffcdd2,stroke:#c62828
    style X4 fill:#fff9c4,stroke:#f9a825
    style G fill:#e3f2fd,stroke:#1565c0
    style L fill:#e8f5e9,stroke:#2e7d32

边缘侧技术选型与配置

2.1 预过滤引擎（默认推荐 Fluent Bit）
选型理由：C语言编写，内存占用5-10MB，ARM生态成熟，断网缓存可靠。
备选方案：若设备为Jetson/RK3588且规则复杂，可选用 Vector（Rust，VRL表达力强）。
关键配置要求：
    启用 storage.type filesystem 磁盘缓冲
    输出批次大小 batch.max_size=10KB，flush间隔=1s
    仅使用 filter/grep/throttle 插件，禁止加载任何AI插件

2.2 SLM推理服务
基座模型：Qwen2.5-1.5B-Instruct-AWQ 或 Llama-3.2-3B-Q4_K_M
推理框架：llama.cpp server 模式
启动参数强制要求：
    bash
    --json-schema '{"type":"object","properties":{"timestamp":{"type":"string"},"service":{"type":"string"},"target_ip":{"type":"string"},"error_code":{"type":"string"},"summary":{"type":"string"}},"required":["timestamp","service","summary"]}'
    --ctx-size 2048 --threads 4 --gpu-layers 99
    API接口：POST /v1/chat/completions，请求体中必须包含 response_format: {"type": "json_object"}

2.3 实体校验兜底脚本
语言：Python 3.10+ 或 Lua（嵌入Fluent Bit）
逻辑：正则提取 (d{1,3}.){3}d{1,3} (IP)、bd{4,5}b (端口)、ERR-d+ (错误码)；缺失字段从原始日志回补。

云端侧技术选型与配置

3.1 知识入库
文档解析：Unstructured / MarkItDown
Embedding模型：bge-m3（1024维，支持中英文+稠密/稀疏双检索）
向量数据库：Milvus 2.x 或 Elasticsearch 8.x+（根据现有基础设施选择）

3.2 RAG Pipeline
编排框架：LlamaIndex（推荐）或 LangChain
检索策略：Hybrid Search = Metadata Filter (target_ip==xxx) + Vector Similarity (summary, top_k=5)
推理模型：Qwen2.5-72B-Instruct（vLLM部署）或 Claude-3.5-Sonnet API
Prompt模板：必须包含 <edge_summary>、<retrieved_cases>、<analysis_instructions> 三段式结构

通信协议
传输协议：MQTT v5（弱网优先）或 Kafka（高吞吐优先）
序列化：MessagePack（比JSON体积小30%，解析快5倍）
安全：mTLS双向证书认证 + Topic级别ACL

实施阶段划分
阶段   周期   交付物   验证方式
Phase 1   2周   预过滤+云端RAG链路（SLM用规则模拟）   云端RAG召回准确率≥80%

Phase 2   3周   边缘SLM上线+实体校验   JSON合法率100%，摘要质量人工评估达标

Phase 3   持续   反馈闭环+Prompt自动迭代   每月摘要信息完整度提升≥5%

Coding Agent 执行指令
⚠️ 给 Agent 的关键提示
实现预过滤时，绝对不要引入 sentence-transformers、openai-embeddings 等任何嵌入模型库。
llama.cpp 服务启动命令必须包含 --json-schema 参数，不可省略。
云端 RAG 检索必须同时使用 metadata filter 和 vector search，不可仅用 vector search。
所有配置文件需提供注释，说明每层过滤的预期拦截率和工程目的。
优先实现 Fluent Bit 方案；仅在用户明确指定时切换为 Vector。
生成的代码需与本文档中的架构图和流程图保持一致，不得自行增删核心节点。
图表是强制性设计约束，不是示意图；若发现图文冲突，以本文档文字描述为准并立即报告。

💡 交付与使用清单
步骤   操作   目的
1   将第一个代码块保存为 requirements.md   定义业务边界与非功能性约束

2   将第二个代码块保存为 technical-design.md   提供含图表的完整技术施工图纸

3   在 Coding Agent 中先上传 requirements.md   建立全局上下文，防止过度设计

4   再上传 technical-design.md 并下达任务   按 Phase 分阶段触发实现

5   每阶段完成后人工验收图表一致性   确保 Agent 未偏离架构设计

备注：两份文档已包含此前讨论的所有要点（Fluent Bit vs Vector 选型结论、四层预过滤逻辑、SLM JSON Schema 强制约束、云端混合检索策略、反馈闭环机制），无需额外补充历史对话内容。