# ADR-0003：边缘 SLM 本地推理与受约束输出

- 状态：已采纳（架构约束）；模型与格式待定
- 日期：2026-11-01
- 关联 PRD：PRD-02
- 代码：[摘要](../services/edge/summarization.md)

## 背景

边缘需要把过滤后的日志转为结构化摘要；系统要求低延迟、可预测输出，并能在网络不可用时继续本地处理。

## 决策

- SLM 在边缘本地推理，参数量不超过 3B。
- 采用 llama.cpp server 作为技术方案中的默认推理服务方向。
- 生成必须受 JSON Schema 或 Grammar 约束；按技术方案要求，启动配置必须包含 `--json-schema`，接口请求使用 JSON 响应格式。
- 当前代码提供 OpenAI-compatible HTTP 摘要器和 server 参数构造器；请求使用 `response_format: {"type":"json_object"}`，Schema 由 server 的 `--json-schema` 参数强制。
- 本地脚本对 IP、端口、错误码进行校验；缺失值只允许从原始日志回补，不得臆造。
- 边缘不运行 Embedding 模型。

## 影响

- 需要对目标硬件上的模型加载、Schema 约束、批处理延迟和资源占用进行实测。
- 技术方案同时列出 AWQ 和 GGUF 候选格式，不能据此推定二者均可被选定的 llama.cpp 版本直接支持。
- 模型文件、推理参数和 Schema 版本需要可独立配置和追踪。

## 待决策

- 在目标硬件和 llama.cpp 版本上选择兼容模型及量化格式。
- 明确设备是否支持 GPU offload，以及 `--gpu-layers` 等参数的硬件适配方式。
- 定义推理超时、服务不可用、Schema 校验失败时的重试、隔离和告警策略。

## 替代方案

- 云端托管 SLM：网络故障时无法保证边缘侧本地结构化处理，不符合本地推理目标。
- 不使用结构化约束、仅依赖 Prompt：无法满足 JSON 合法率 100% 的要求，不采用。