#!/bin/bash
# 主机健康检查 - 建议通过 crontab 每分钟运行
# 检查 pyWork 和 Litestream 是否正常
set -e

PYWORK_URL="${PYWORK_URL:-http://localhost:8080/}"
LITESTREAM_SERVICE="${LITESTREAM_SERVICE:-litestream}"
ALERT_EMAIL="${ALERT_EMAIL:-}"
LOG="/var/log/pywork-health.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

send_alert() {
    local subject="$1"
    local body="$2"
    log "ALERT: $subject - $body"
    if [[ -n "$ALERT_EMAIL" ]] && command -v mail &>/dev/null; then
        echo "$body" | mail -s "$subject" "$ALERT_EMAIL"
    fi
}

# 检查 pyWork HTTP
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PYWORK_URL" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" != "200" ]]; then
    send_alert "[pyWork DOWN]" "HTTP status: $HTTP_CODE"
else
    log "pyWork OK (HTTP $HTTP_CODE)"
fi

# 检查 Litestream 服务
if ! systemctl is-active --quiet "$LITESTREAM_SERVICE"; then
    send_alert "[Litestream DOWN]" "Service $LITESTREAM_SERVICE is not active"
else
    log "Litestream OK"
fi
