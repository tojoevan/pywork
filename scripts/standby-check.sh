#!/bin/bash
# 备机数据库新鲜度检查 - 建议通过 crontab 每 5 分钟运行
# 检查备机数据库最后修改时间，超过阈值则告警
set -e

DB_PATH="${PYWORK_DB_PATH:-/data/pywork/pywork.db}"
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

if [[ ! -f "$DB_PATH" ]]; then
    send_alert "[Standby DB MISSING]" "Database file not found: $DB_PATH"
    exit 1
fi

LAST_MOD=$(stat -c %Y "$DB_PATH" 2>/dev/null || stat -f %m "$DB_PATH" 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE=$((NOW - LAST_MOD))

if [[ "$AGE" -gt "$MAX_AGE" ]]; then
    send_alert "[Replication STALE]" "Standby DB is ${AGE}s old (max ${MAX_AGE}s)"
else
    log "DB freshness OK (${AGE}s old)"
fi
