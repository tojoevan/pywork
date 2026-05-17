#!/bin/bash
# 备机数据库新鲜度检查 - 建议通过 crontab 每 5 分钟运行
# 检查 LTX replica 目录中最新文件的时间戳，超过阈值则告警
#
# 注意: 备机的 pywork.db-replica 是 Litestream LTX 目录，不是单个 .db 文件
set -e

REPLICA_PATH="${REPLICA_PATH:-/www/wwwroot/pywork/data/pywork.db-replica}"
MAX_AGE="${MAX_AGE:-300}"  # 默认 5 分钟
ALERT_EMAIL="${ALERT_EMAIL:-}"
LOG="/var/log/pywork-standby.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

send_alert() {
    local subject="$1"
    local body="$2"
    log "ALERT: $subject - $body"
    if [[ -n "$ALERT_EMAIL" ]] && command -v mail &>/dev/null; then
        echo "$body" | mail -s "$subject" "$ALERT_EMAIL"
    fi
}

if [[ ! -d "$REPLICA_PATH" ]]; then
    send_alert "[Replica MISSING]" "Replica directory not found: $REPLICA_PATH"
    exit 1
fi

# 获取 LTX 目录中最新文件的修改时间
LTX_DIR="${REPLICA_PATH}/ltx"
if [[ ! -d "$LTX_DIR" ]]; then
    send_alert "[LTX MISSING]" "LTX directory not found: $LTX_DIR"
    exit 1
fi

LAST_MOD=$(find "$LTX_DIR" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
if [[ -z "$LAST_MOD" ]]; then
    send_alert "[No LTX files]" "No LTX files found in $LTX_DIR"
    exit 1
fi

NOW=$(date +%s)
AGE=$((NOW - LAST_MOD))

if [[ "$AGE" -gt "$MAX_AGE" ]]; then
    send_alert "[Replication STALE]" "Standby LTX data is ${AGE}s old (max ${MAX_AGE}s)"
else
    log "Replication freshness OK (${AGE}s old)"
fi
