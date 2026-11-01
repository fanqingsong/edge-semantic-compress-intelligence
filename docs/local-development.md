# 本地开发

本页是本地测试、Compose 启动、知识入库和反馈审核的操作入口。项目概览与文档索引见 [README](../README.md)。

需要 Python 3.11 或更高版本。当前代码切片仅使用 Python 标准库，可直接运行测试：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

需要运行真实服务集成测试时，安装 `.[milvus,transport,documents]` 并先生成本地开发证书：

```bash
bash scripts/generate-dev-mqtt-certs.sh
docker compose up -d --build --wait
RUN_MQTT_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_mqtt_integration -v
RUN_MILVUS_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_milvus_integration -v
RUN_FLUENT_BIT_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_fluentbit_integration -v
docker compose stop
```

集成测试使用临时 SQLite 数据库和唯一 Milvus collection，并在测试结束时清理；Fluent Bit 测试覆盖 JSONL 文件 Tail 与 UDP Syslog 输入。

边缘事件契约定义在 [`schemas/edge-event-v1.schema.json`](../schemas/edge-event-v1.schema.json)。预过滤 MVP 接收包含 `timestamp`、`service`、`message` 的 JSON Lines 记录；具体输入适配器可在后续接入 Fluent Bit。当前摘要器和 RAG 模型均为确定性 mock，不执行真实模型推理。云端 adapter 可初始化兼容的 Milvus 集合；实际检索/入库仍需运行 Milvus 和 bge-m3 HTTP 服务。

端口回补仅从显式端口字段或带端口标签的日志文本提取，避免将其他数字误当作端口。

安装云端、传输和文档解析适配器依赖：

```bash
python3 -m pip install -e '.[milvus,transport,documents]'
```

先运行 `bash scripts/generate-dev-mqtt-certs.sh`，再用 `docker compose up -d --build` 启动 Edge Agent、Fluent Bit、Cloud RAG Agent、Mosquitto、Milvus 及其依赖。MQTT 使用 mTLS TLS 8883：Edge 证书只可发布 `edge/events`，Cloud 证书只可订阅该主题；匿名和明文连接不开放。开发证书仅供本地使用，不能用于生产。Fluent Bit 读取 `./examples/logs/*.jsonl` 并监听 UDP Syslog 5514。开发环境默认使用 mock SLM、embedding 和分析模型；设置 `EDGE_SUMMARIZER=llama_cpp` 并配置 `EDGE_LLAMA_URL` 可接入本地 llama.cpp，云端模式可通过 `CLOUD_EMBEDDING_MODE`、`CLOUD_EMBEDDING_URL`、`CLOUD_ANALYSIS_MODE`、`CLOUD_ANALYSIS_URL` 配置。SQLite outbox 默认上限为 100 MiB，满载时拒绝新消息。

导入样例或实际运维文档（Markdown、TXT、JSONL、PDF、DOCX、PPTX、HTML）：将文件放入 `examples/knowledge/sources` 或挂载到该目录，再运行：

```bash
docker compose --profile tools run --rm knowledge-ingest
```

文档解析要求显式 `Summary` 和 `Resolution` 字段；字段不足时会报错，不会让模型补写事实。可用以下命令审核建议：

```bash
docker compose --profile tools run --rm feedback-admin
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 review <suggestion-id> --approve --reviewer <name> --note "validated against labeled cases"
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 publish <suggestion-id>
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 weekly-report
```

`publish` 只记录人工确认状态，不会远程推送或自动替换 Edge Prompt。
