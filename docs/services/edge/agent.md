# edge agent

Code: [`services/edge-agent/src/edge/agent`](../../../services/edge-agent/src/edge/agent)

Process: `edge-log-agent`. The Compose service name is `edge-agent`. It listens on `8090`.

## Responsibilities

This is the only long-running process on the edge. It does not implement filtering, summarization, or transport rules. A LangGraph state graph calls them in order, once per service after filtering:

1. [Filtering](filtering.md)
2. [Summarization](summarization.md), one event per service
3. [Transport](transport.md)

Fluent Bit `POST`s a log batch to `/v1/logs`. How that batch is formed is [Log collection](collection.md). The body is UTF-8 log lines, with a default limit of 1 MiB. `GET /healthz` means only that the process is alive. It does not mean the outbox is empty or that the cloud has processed the events. `GET /v1/status` returns the outbox pending count and byte count. It does not return event payloads.

Local startup is in [local development](../../local-development.md).
