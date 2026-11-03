# Log collection

Configuration: [`deploy/fluent-bit`](../../../deploy/fluent-bit)

Related: [edge agent](agent.md), [Filtering](filtering.md), [ADR-0002](../../adr/adr-0002-edge-collector.md)

The Compose service is `fluent-bit` (`fluent/fluent-bit:3.2.10`). It is not a Python service. It collects logs, drops `info` records, and posts what remains to the edge agent. Rule filtering (L1–L4) stays in [filtering](filtering.md).

## Inputs

Two inputs run at the same time. Routing uses tags, not the order of the sections.

| Source | Plugin | Tag | What it reads |
|---|---|---|---|
| `/var/log/edge/*.jsonl` | `tail` | `edge.file` | One JSON object per line |
| UDP `5514` | `syslog` | `edge.syslog` | RFC 5424 datagrams |

Compose mounts `./examples/logs` read-only at `/var/log/edge`, and publishes `5514/udp`. A file line is expected to already look like a downstream record: non-empty `timestamp`, `service`, and `message`, plus optional `level`, `status_code`, `target_ip`, `target_port`, and `error_code`.

`tail` stores the read offset in `/var/lib/fluent-bit/tail.db` on the `fluent_bit_state` volume. A restart continues from that offset. A file with no stored offset is read from the start (`Read_from_Head`). The path is rescanned every 1 second. After a rotation, the old file is followed for up to 30 seconds. Lines longer than the internal buffer are skipped.

Syslog is connectionless UDP. Fluent Bit sees a record only after some sender writes to this port. The built-in `syslog-rfc5424` parser splits fields such as `time`, `host`, `ident`, and `message`.

## Normalization

The Lua filter matches only `edge.syslog`. `edge.file` does not enter it. `normalize_syslog.lua` replaces the record with the same shape as a file line:

| Field | Source |
|---|---|
| `timestamp` | `time` on the record, or the event time as UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `service` | `ident`, otherwise `host`, otherwise `syslog` |
| `message` | `message`, otherwise `msg`, otherwise an empty string |
| `level` | `level` or `severity`, otherwise the low 3 bits of PRI (`0` emerg … `6` info … `7` debug) |
| `status_code`, `target_ip`, `target_port`, `error_code` | Copied only when the parser already produced that key |

Keys that are not copied (`pid`, `msgid`, `pri`, and the rest) are absent from the outgoing record. The script does not drop records. Dropping `info` is the next filter.

## What leaves the process

A grep filter matches `edge.*` and excludes `level` values `info` and `informational`, case-insensitive. Other levels, and records with no `level`, continue. `debug` is forwarded.

Both tags then match one HTTP output:

```text
POST http://edge-agent:8090/v1/logs
```

`edge-agent` is the Compose DNS name. Fluent Bit starts only after the edge agent's `GET /healthz` check passes. The body format is `json_lines`: one JSON object per line. The engine writes its own event time into the `timestamp` field as ISO 8601.

## How a batch is formed

There is no fixed record count. [`fluent-bit.conf`](../../../deploy/fluent-bit/fluent-bit.conf) sets `Flush 1`, so about once per second the engine hands every record collected in that interval to the HTTP output as one request:

```text
{"timestamp":"...","service":"api","level":"error","message":"..."}
{"timestamp":"...","service":"db","level":"warning","message":"..."}
```

An empty interval produces no request. `Workers 1` means one sender thread. `Retry_Limit no_limits` keeps retrying a failed chunk instead of dropping it after a fixed number of attempts. Filesystem buffering is not enabled (`storage.type` is unset), so a backlog of unsent chunks stays in memory. `tail.db` records only how far each file was read. It does not store records that have not been sent yet.

On shutdown, `Grace 30` waits up to 30 seconds to flush records already in memory.

## What the edge agent accepts

`POST /v1/logs` requires `Content-Length`. The body must be non-empty UTF-8 and at most 1 MiB. The handler splits on lines, drops blank lines, and passes the remaining lines to `EdgeRuntime.process_batch`. A successful response includes `event_count`, `published`, `pending`, and `dropped` counts by reason. From there, filtering, summarization, and MQTT delivery are the [edge agent](agent.md) path, not Fluent Bit.
