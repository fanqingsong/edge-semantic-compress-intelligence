# 本地开发

本页按服务说明如何测试和启动。服务职责见 [服务目录](services/README.md)，项目概览见 [README](../README.md)。

需要 Python 3.11 或更高版本。不依赖外部服务的测试可直接运行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

需要真实服务时，安装可选依赖并先生成本地开发证书：

```bash
python3 -m pip install -e '.[milvus,transport,documents]'
bash scripts/generate-dev-mqtt-certs.sh
```

## edge agent

[edge agent](services/edge/agent.md) 组装 [过滤](services/edge/filtering.md)、[摘要](services/edge/summarization.md) 和 [传输](services/edge/transport.md)。

```bash
docker compose up -d --build --wait
```

Fluent Bit 读取 `./examples/logs/*.jsonl`，并监听 UDP Syslog `5514`，再 `POST` 到 edge agent 的 `8090`。开发环境默认使用 mock 摘要。设置 `EDGE_SUMMARIZER=llama_cpp` 并配置 `EDGE_LLAMA_URL` 可接入本地 llama.cpp。SQLite outbox 默认上限为 100 MiB，满载时拒绝新消息。

MQTT 使用 mTLS，端口 `8883`。edge agent 证书只可发布 `edge/events`，cloud agent 证书只可订阅该主题。匿名和明文连接不开放。开发证书仅供本地使用。

传输与采集的集成测试：

```bash
RUN_MQTT_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_mqtt_integration -v
RUN_FLUENT_BIT_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_fluentbit_integration -v
```

端口回补只从显式端口字段或带端口标签的日志文本提取。

## cloud agent

[cloud agent](services/cloud/agent.md) 订阅边缘事件，并调用 [检索](services/cloud/retrieval.md) 和 [RAG](services/cloud/rag.md)。它与 edge agent 一起由上面的 `docker compose up` 启动。Milvus 依赖 etcd 和 MinIO。

开发环境默认使用 mock embedding 和分析模型。可通过 `CLOUD_EMBEDDING_MODE`、`CLOUD_EMBEDDING_URL`、`CLOUD_ANALYSIS_MODE`、`CLOUD_ANALYSIS_URL` 切换。

检索适配器的集成测试：

```bash
RUN_MILVUS_INTEGRATION=1 PYTHONPATH=src python3 -m unittest tests.test_milvus_integration -v
```

集成测试使用临时 SQLite 数据库和唯一 Milvus collection，并在结束时清理。

## 知识入库

[知识入库](services/cloud/knowledge.md) 不随主链路常驻。把 Markdown、TXT、JSONL、PDF、DOCX、PPTX 或 HTML 放入 `examples/knowledge/sources`，然后运行：

```bash
docker compose --profile tools run --rm knowledge-ingest
```

文档必须有显式的 `Summary` 和 `Resolution`。字段不足时会报错，不会让模型补写事实。

## 反馈

[反馈](services/cloud/feedback.md) 的审核 CLI 同样使用 `tools` profile：

```bash
docker compose --profile tools run --rm feedback-admin
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 review <suggestion-id> --approve --reviewer <name> --note "validated against labeled cases"
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 publish <suggestion-id>
docker compose --profile tools run --rm feedback-admin --db /var/lib/cloud/feedback.sqlite3 weekly-report
```

`publish` 只记录人工确认状态，不会远程推送或自动替换边缘 Prompt。

停止本地栈：

```bash
docker compose stop
```
