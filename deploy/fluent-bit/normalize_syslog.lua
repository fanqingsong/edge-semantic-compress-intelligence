local SEVERITY_NAME = {
    [0] = "emerg",
    [1] = "alert",
    [2] = "crit",
    [3] = "error",
    [4] = "warning",
    [5] = "notice",
    [6] = "info",
    [7] = "debug",
}

local function syslog_level(record)
    local explicit = record["level"] or record["severity"]
    if explicit ~= nil and explicit ~= "" then
        return tostring(explicit):lower()
    end
    local pri = tonumber(record["pri"])
    if pri == nil then
        return nil
    end
    return SEVERITY_NAME[pri % 8]
end

function normalize_syslog(tag, timestamp, record)
    local log_time = record["time"]
    if log_time == nil or log_time == "" then
        log_time = os.date("!%Y-%m-%dT%H:%M:%SZ", timestamp)
    end

    local normalized = {
        timestamp = log_time,
        service = record["ident"] or record["host"] or "syslog",
        message = record["message"] or record["msg"] or "",
    }
    local level = syslog_level(record)
    if level ~= nil then
        normalized["level"] = level
    end

    for _, key in ipairs({"status_code", "target_ip", "target_port", "error_code"}) do
        if record[key] ~= nil then
            normalized[key] = record[key]
        end
    end

    return 1, timestamp, normalized
end