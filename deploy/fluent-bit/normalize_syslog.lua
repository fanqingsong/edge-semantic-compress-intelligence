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

    for _, key in ipairs({"status_code", "target_ip", "target_port", "error_code"}) do
        if record[key] ~= nil then
            normalized[key] = record[key]
        end
    end

    return 1, timestamp, normalized
end