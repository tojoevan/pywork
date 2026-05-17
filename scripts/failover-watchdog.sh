#!/bin/bash
# 自动故障检测与切换守护脚本 - 在备机上常驻运行
# 定时探测主机 pyWork 可用性，连续失败后自动执行故障切换
#
# 配合 rsync + litestream restore 方案：
# - 备机通过 rsync 从主机拉取 LTX replica 目录
# - 故障切换时用 litestream restore 从本地 LTX 目录恢复 .db 文件
#
# 环境变量:
#   PRIMARY_IP       (必填) 主机 IP
#   PRIMARY_PORT     主机 pyWork 端口 (默认 8080)
#   DB_PATH          数据库路径 (默认 /www/wwwroot/pywork/data/pywork.db)
#   REPLICA_PATH     rsync 同步的 replica 目录 (默认 /www/wwwroot/pywork/data/pywork.db-replica)
#   LITESTREAM_CONFIG litestream 配置文件 (默认 /etc/litestream.yml)
#   CHECK_INTERVAL   检测间隔秒数 (默认 10)
#   MAX_FAILURES     连续失败次数阈值 (默认 3)
#   PYWORK_SERVICE   pyWork systemd 服务名 (默认 pywork)

PRIMARY_IP="${PRIMARY_IP:-}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"
DB_PATH="${DB_PATH:-/www/wwwroot/pywork/data/pywork.db}"
REPLICA_PATH="${REPLICA_PATH:-/www/wwwroot/pywork/data/pywork.db-replica}"
LITESTREAM_CONFIG="${LITESTREAM_CONFIG:-/etc/litestream.yml}"
CHECK_INTERVAL="${CHECK_INTERVAL:-10}"
MAX_FAILURES="${MAX_FAILURES:-3}"
PYWORK_SERVICE="${PYWORK_SERVICE:-pywork}"
LOG="/var/log/pywork-failover.log"

failures=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# 检测主机 pyWork 是否可达
check_primary() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 5 --max-time 10 \
        "http://${PRIMARY_IP}:${PRIMARY_PORT}/" 2>/dev/null || echo "000")
    [[ "$http_code" == "200" ]]
}

# 执行故障切换
do_failover() {
    log "=== AUTO FAILOVER triggered ==="

    # 1. 检查 replica 目录
    if [[ ! -d "$REPLICA_PATH" ]]; then
        log "ERROR: Replica directory not found: $REPLICA_PATH"
        exit 1
    fi

    # 2. 从 LTX 目录 restore 数据库
    log "Restoring database from $REPLICA_PATH ..."
    rm -f /tmp/failover-restore.db
    if ! litestream restore -config "$LITESTREAM_CONFIG" -o /tmp/failover-restore.db "$DB_PATH" 2>>"$LOG"; then
        log "ERROR: litestream restore failed"
        exit 1
    fi

    # 3. 验证恢复的数据库完整性
    log "Checking restored database integrity..."
    local integrity
    integrity=$(sqlite3 /tmp/failover-restore.db "PRAGMA integrity_check;" 2>&1)
    if [[ "$integrity" != "ok" ]]; then
        log "ERROR: Database integrity check failed: $integrity"
        rm -f /tmp/failover-restore.db
        exit 1
    fi
    log "Database integrity: OK"

    # 4. 替换数据库文件
    if [[ -e "$DB_PATH" ]]; then
        log "Removing old db: $DB_PATH"
        rm -rf "$DB_PATH"
    fi
    mv /tmp/failover-restore.db "$DB_PATH"
    chown pywork:pywork "$DB_PATH"
    log "Database restored: $DB_PATH"

    # 5. WAL checkpoint
    sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>>"$LOG"

    # 6. 启动 pyWork
    log "Starting pyWork..."
    systemctl start "$PYWORK_SERVICE"

    # 7. 验证启动
    sleep 3
    if systemctl is-active --quiet "$PYWORK_SERVICE"; then
        local check_code
        check_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PRIMARY_PORT}/" 2>/dev/null || echo "000")
        if [[ "$check_code" == "200" ]]; then
            log "pyWork is running and responding (HTTP $check_code)"
        else
            log "WARN: pyWork is running but HTTP check returned $check_code"
        fi
    else
        log "ERROR: pyWork failed to start"
        journalctl -u "$PYWORK_SERVICE" -n 20 --no-pager >> "$LOG"
        exit 1
    fi

    local standby_ip
    standby_ip=$(hostname -I | awk '{print $1}')
    log "=== AUTO FAILOVER complete ==="
    log "ACTION REQUIRED: Switch DNS from $PRIMARY_IP to $standby_ip"
}

# --- 主循环 ---

if [[ -z "$PRIMARY_IP" ]]; then
    echo "ERROR: PRIMARY_IP is required. Set it in the service environment."
    exit 1
fi

log "Watchdog started: monitoring $PRIMARY_IP:$PRIMARY_PORT (interval=${CHECK_INTERVAL}s, threshold=${MAX_FAILURES})"

while true; do
    if check_primary; then
        if [[ "$failures" -gt 0 ]]; then
            log "Primary recovered (was $failures failures)"
        fi
        failures=0
    else
        failures=$((failures + 1))
        log "Primary unreachable ($failures/$MAX_FAILURES)"

        if [[ "$failures" -ge "$MAX_FAILURES" ]]; then
            do_failover
            exit 0
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
