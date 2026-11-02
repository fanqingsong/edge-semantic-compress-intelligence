# edge agent

Code: [`services/edge-agent/src/edge/agent`](../../../services/edge-agent/src/edge/agent)

Process: `edge-log-agent`. The Compose service name is `edge-agent`. It listens on `8090`.

## Responsibilities

This is the only long-running process on the edge. It does not implement filtering, summarization, or transport rules. A LangGraph state graph calls them in order, once per service after filtering. The HTTP interface is unchanged:

1. [Filtering](filtering.md)
2. [Summarization](summarization.md), one event per service
3. [Transport](transport.md)

Fluent Bit `POST`s a log batch to `/v1/logs`. The body is UTF-8 log lines, with a default limit of 1 MiB. `GET /healthz` means only that the process is alive. It does not mean the outbox is empty or that the cloud has processed the events.

Local startup and certificates are in [local development](../../local-development.md).
