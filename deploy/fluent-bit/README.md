# Fluent Bit 配置学习笔记

对照文件：[`fluent-bit.conf`](fluent-bit.conf)、[`normalize_syslog.lua`](normalize_syslog.lua)。

镜像版本见 [`compose.yaml`](../../compose.yaml) 里的 `fluent/fluent-bit:3.2.10`。这份配置负责采集，并在转发前丢掉 `info` 级别。规则过滤（L1–L4）在 edge agent 里，不在这里。批量如何形成并交给 edge agent，见 [Log collection](../../docs/services/edge/collection.md)。

## 这条流水线在做什么

Fluent Bit 按固定顺序处理一条日志：

1. **Input** 把外部日志变成内部事件。事件带一个 **Tag**（标签）和一个时间戳，正文是一组键值。
2. **Filter** 只处理标签匹配的事件，可以改写键值。
3. **Output** 把标签匹配的事件发出去。

本文件里有两条入口、两个过滤器、一个出口：

```text
/var/log/edge/*.jsonl
        │  tail，标签 edge.file
        │
        ├──────────────────────────────┐
        │                              │
UDP 5514 syslog                        │  lua 只匹配 edge.syslog
        │  syslog，标签 edge.syslog    │
        └──────────────► normalize ────┤
                                       ▼
                          grep：丢掉 level 为 info 的事件
                                       ▼
                          HTTP POST edge-agent:8090/v1/logs
                          正文是 JSON Lines，标签 edge.*
```

`edge.file` 不经过 Lua。文件里的 JSON 被认为已经接近下游格式。`edge.syslog` 先被 Lua 收成同一套字段，并带上 `level`。两条路径再一起经过级别过滤，然后送出。

## 配置文件怎么读

Fluent Bit 的主配置是若干个方括号段。段名是插件类型，段内是该插件的键值。键和值之间用空格分开，大小写不敏感，习惯写成 `Name`、`Match` 这种形式。

同一类型可以出现多次。本文件有两个 `[INPUT]`，它们同时工作，互不覆盖。

路由不靠“写在一起”，靠 **Tag** 和 **Match**：

| 段 | 用什么连接 | 本文件里的值 |
|---|---|---|
| `[INPUT]` | `Tag`，给事件贴标签 | `edge.file`、`edge.syslog` |
| `[FILTER]` | `Match`，决定处理谁 | `edge.syslog`，然后 `edge.*` |
| `[OUTPUT]` | `Match`，决定发送谁 | `edge.*` |

`edge.*` 是通配。`edge.file` 和 `edge.syslog` 都会进入级别过滤和同一个 HTTP 输出。`edge.file` 对不上 `edge.syslog`，所以不会进 Lua。

## `[SERVICE]`

```1:5:deploy/fluent-bit/fluent-bit.conf
[SERVICE]
    Flush                     1
    Grace                     30
    Log_Level                 info
    Parsers_File              parsers.conf
```

这是进程级设置，不是某条日志的处理规则。

| 键 | 含义 |
|---|---|
| `Flush` | 每隔多少秒把内存里攒下的事件交给输出插件。这里是 1 秒。数值越小，日志越快离开本进程，CPU 唤醒也更频繁。 |
| `Grace` | 收到停止信号后，最多再等多少秒把缓冲区发出去。这里是 30 秒。容器停止时，这是“尽量把已读日志送完”的窗口。 |
| `Log_Level` | Fluent Bit **自己的**运行日志级别，不是被采集的业务日志。`info` 会看到启动、插件加载和一般错误。排查采集问题时可临时改成 `debug`。 |
| `Parsers_File` | 解析器定义文件。路径相对主配置所在目录。容器里主配置在 `/fluent-bit/etc/fluent-bit.conf`，所以实际读的是镜像自带的 `/fluent-bit/etc/parsers.conf`。仓库没有覆盖这个文件。 |

后面 Input 里的 `Parser json` 和 `Parser syslog-rfc5424` 都是这个自带文件里的名字。解析器负责把一行原文拆成键值；它不决定日志送到哪里。

## 文件输入：`tail`

```7:16:deploy/fluent-bit/fluent-bit.conf
[INPUT]
    Name                      tail
    Tag                       edge.file
    Path                      /var/log/edge/*.jsonl
    Parser                    json
    DB                        /var/lib/fluent-bit/tail.db
    Read_from_Head            true
    Refresh_Interval           1
    Rotate_Wait               30
    Skip_Long_Lines           On
```

`tail` 类似持续执行 `tail -F`：盯住文件末尾的新行，并在轮转后跟上新文件。

| 键 | 含义 |
|---|---|
| `Name` | 插件名。`tail` 表示按行读文件。 |
| `Tag` | 每条事件的标签，固定为 `edge.file`。 |
| `Path` | 只读 `/var/log/edge/` 下、后缀是 `.jsonl` 的文件。`*` 不跨目录。 |
| `Parser` | 用内置 `json` 解析器。每一行必须是一个 JSON 对象，对象的键会变成事件字段。 |
| `DB` | 用 SQLite 记住每个文件已经读到的偏移。进程重启后从上次位置继续，避免把同一行再送一遍。 |
| `Read_from_Head` | 某个文件在 DB 里还没有偏移时，从文件头开始读。已有偏移的文件仍从偏移处继续。 |
| `Refresh_Interval` | 每隔 1 秒重新扫描 `Path`，以便发现新出现的 `.jsonl`。 |
| `Rotate_Wait` | 文件被轮转（改名或替换）后，最多再盯旧文件 30 秒，把轮转前刚写入的行读完。 |
| `Skip_Long_Lines` | 超过内部缓冲块长度的行直接跳过，避免一行超长日志拖住采集。 |

Compose 把仓库的 `examples/logs` 只读挂到容器的 `/var/log/edge`，把命名卷 `fluent_bit_state` 挂到 `/var/lib/fluent-bit`。所以：

- 把样例 `.jsonl` 放到 `examples/logs/`，就是在喂这条 Input。
- `tail.db` 在卷里，容器重建后偏移还在。删掉这个卷才会重新从头读。

文件行应当已经是下游要的 JSON 对象，至少包含非空字符串 `timestamp`、`service`、`message`。可选字段是 `level`、`status_code`、`target_ip`、`target_port`、`error_code`。`level` 为 `info` 或 `informational` 时，后面的 grep 过滤器会丢掉这一行，不会发给 edge agent。没有 `level` 的行会转发。edge agent 的格式检查在 `services/edge-agent/src/edge/filtering/service.py` 的 `LogRecord.from_json_line`。不符合的行会被过滤层以 `invalid_format` 丢掉，Fluent Bit 本身仍会把它发出去。

## Syslog 输入

```18:24:deploy/fluent-bit/fluent-bit.conf
[INPUT]
    Name                      syslog
    Tag                       edge.syslog
    Mode                      udp
    Listen                    0.0.0.0
    Port                      5514
    Parser                    syslog-rfc5424
```

| 键 | 含义 |
|---|---|
| `Name` | `syslog` 插件，在本进程里开一个日志接收口。 |
| `Tag` | 收到的每条事件标签为 `edge.syslog`。 |
| `Mode` | `udp`。报文无连接，也没有 TCP 那种“对方还在”的确认。 |
| `Listen` | `0.0.0.0` 表示监听容器全部网卡。 |
| `Port` | 容器内 UDP `5514`。Compose 把它发布到宿主机的 `5514/udp`。 |
| `Parser` | `syslog-rfc5424` 按 RFC 5424 拆字段。常见结果包括 `time`、`host`、`ident`、`pid`、`msgid`、`message`。 |

这不是文件采集。应用或日志代理把 syslog 发到这个 UDP 端口，Fluent Bit 才看得到。

## Lua 过滤器：只整理 syslog

```26:30:deploy/fluent-bit/fluent-bit.conf
[FILTER]
    Name                      lua
    Match                     edge.syslog
    Script                    /fluent-bit/etc/normalize_syslog.lua
    Call                      normalize_syslog
```

| 键 | 含义 |
|---|---|
| `Name` | 使用 `lua` 过滤器，用一段脚本改写事件。 |
| `Match` | 只有标签 `edge.syslog` 会进入脚本。 |
| `Script` | 脚本在容器内的绝对路径。Compose 把仓库里的 `normalize_syslog.lua` 挂到这里，只读。 |
| `Call` | 每条匹配事件调用函数 `normalize_syslog`。 |

函数签名是 Fluent Bit 规定的三个参数：`tag`、`timestamp`、`record`。`record` 是解析后的字段表。返回三个值：

```lua
return 1, timestamp, normalized
```

第一个数是处理结果码。`-1` 丢掉这条事件。`0` 保留原记录。`1` 用返回的时间戳和 `record` 替换原事件。`2` 只替换 `record`。这个脚本固定返回 `1`，不在这里丢弃。丢弃 `info` 交给后面的 grep。

脚本把 syslog 字段收成和文件日志相同的形状：

| 输出字段 | 来源 |
|---|---|
| `timestamp` | 优先用记录里的 `time`。没有或是空字符串时，用事件时间戳格式化成 UTC 的 `YYYY-MM-DDTHH:MM:SSZ`。 |
| `service` | `ident`，否则 `host`，再否则字面量 `syslog`。 |
| `message` | `message`，否则 `msg`，再否则空字符串。 |
| `level` | 已有的 `level` 或 `severity`，否则用 PRI 的低 3 位：0 emerg、1 alert、2 crit、3 error、4 warning、5 notice、6 info、7 debug。都没有时不写这个字段。 |
| `status_code`、`target_ip`、`target_port`、`error_code` | 仅当解析结果里已经有同名键时才复制。 |

标准 syslog 正文通常只落在 `message` 里，不会自动出现 `status_code` 这几个键。它们是为了和文件 JSON 的可选字段对齐；解析器没给出时，脚本不会凭空制造。

未被复制的原始键（例如 `pid`、`msgid`、`pri`）不会出现在送出的记录里，因为脚本返回的是一张新表，不是在原表上打补丁。

## Grep 过滤器：丢掉 info

```32:36:deploy/fluent-bit/fluent-bit.conf
# Drop info-level logs. Records with any other level, or with no level, are kept.
[FILTER]
    Name                      grep
    Match                     edge.*
    Exclude                   level ^(?i)(info|informational)$
```

| 键 | 含义 |
|---|---|
| `Name` | `grep` 按字段内容决定保留或丢弃，不改写其他字段。 |
| `Match` | `edge.*`。文件日志和已经规范化的 syslog 都经过这里。 |
| `Exclude` | 字段 `level` 整值匹配 `info` 或 `informational` 时丢掉该事件，大小写不敏感。`warning`、`error`、`debug`、`notice` 以及其他级别会继续送出。没有 `level` 的事件不匹配这条规则，也会送出。 |

因此 Fluent Bit 发给 edge agent 的日志里，不会再有 info 级别。`debug` 比 info 更低，但仍会转发；若只要 warning 及以上，需要再收紧这条正则。

## HTTP 输出

```38:48:deploy/fluent-bit/fluent-bit.conf
[OUTPUT]
    Name                      http
    Match                     edge.*
    Host                      edge-agent
    Port                      8090
    URI                       /v1/logs
    Format                    json_lines
    Json_Date_Key             timestamp
    Json_Date_Format          iso8601
    Retry_Limit               no_limits
    Workers                   1
```

| 键 | 含义 |
|---|---|
| `Name` | `http` 输出。对匹配事件发 HTTP 请求。 |
| `Match` | `edge.*`，两条输入最终都走这里。 |
| `Host` | `edge-agent`。这是 Compose 网络里的服务名，由 Docker DNS 解析，不是宿主机上的名字。 |
| `Port` | edge agent 监听的 `8090`。 |
| `URI` | `POST /v1/logs`。agent 只接受这个路径；别的路径返回 404。 |
| `Format` | `json_lines`：请求体是多行文本，每一行一个 JSON 对象。agent 按行拆开再解析。 |
| `Json_Date_Key` | 序列化时，用字段名 `timestamp` 写下 Fluent Bit 的事件时间。 |
| `Json_Date_Format` | 这个时间写成 ISO 8601。 |
| `Retry_Limit` | `no_limits` 表示发送失败后持续重试，不因为次数用尽而丢弃这批事件。 |
| `Workers` | 这个输出使用 1 个工作线程。 |

`Host edge-agent` 能通，是因为 Compose 把 `fluent-bit` 放在和 `edge-agent` 同一个网络，并且 `depends_on` 要求 agent 的健康检查通过后才启动 Fluent Bit。健康检查打的是 agent 的 `GET /healthz`。

agent 对请求体还有限制：必须带 `Content-Length`，正文是 UTF-8，不能为空，最大 1 MiB。成功处理后返回 JSON，里面有 `event_count`、`published`、`pending` 和按原因统计的 `dropped`。

## 和本仓库其他部分的边界

采集停在 HTTP 发出去的那一刻。

- 偏移保存在 `tail.db`。这只回答“文件读到哪一行”，不保存还没发出去的业务日志。
- 本文件没有打开 Fluent Bit 的文件系统缓冲（`storage.type filesystem`）。发送失败时的堆积使用插件默认的内存重试。
- L1 格式、L2 成功状态、L3 关键词、L4 重复抑制都在 [`docs/services/edge/filtering.md`](../../docs/services/edge/filtering.md) 描述的过滤模块里。
- 选择 Fluent Bit 而不是 Vector 的原因在 [ADR-0002](../../docs/adr/adr-0002-edge-collector.md)。

## 建议的阅读顺序

1. 先看两个 `Tag` 和一个 `Match edge.*`，确认文件日志和 syslog 在出口汇合。
2. 再看 Lua 的 `Match edge.syslog`，确认只有 syslog 被改写。
3. 看紧随其后的 grep：`Match edge.*`，`Exclude level` 为 info。这是“只转发非 info 日志”的位置。
4. 打开 `normalize_syslog.lua`，对照脚本输出的三个必填字段、`level`，以及过滤模块要求的三个必填字段。
5. 最后看 Compose 里的三个挂载：主配置、Lua 脚本、`examples/logs`。改配置后需要重建或重启 `fluent-bit` 容器，挂载的文件才会按容器启动时的内容被进程读到。
