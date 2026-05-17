#!/bin/bash
# 故障切换脚本 - 在备机上运行
# 用法: ./failover.sh [--force]
# --force: 跳过主机可达性检查，直接执行切换
#
# 配合 rsync + litestream restore 方案
#
# 环境变量:
#   PRIMARY_IP       主机 IP（用于可达性检查）
#   DB_PATH          数据库路径 (默认 /www/wwwroot/pywork/data/pywork.db)
#   REPLICA_PATH     rsync 同步的 replica 目录 (默认 /www/wwwroot/pywork/data/pywork.db-replica)
#   LITESTREAM_CONFIG litestream 配置文件 (默认 /etc/litestream.yml)
#   PRIMARY_PORT     主机 pyWork 端口 (默认 8080)
#   PYWORK_SERVICE   pyWork systemd 服务名 (默认 pywork)

DB_PATH="${DB_PATH:-/www/wwwroot/pywork/data/pywork.db}"
REPLICA_PATH="${REPLICA_PATH:-/www/wwwroot/pywork/data/pywork.db-replica}"
LITESTREAM_CONFIG="${LITESTREAM_CONFIG:-/etc/litestream.yml}"
PYWORK_SERVICE="${PYWORK_SERVICE:-pywork}"
PRIMARY_PORT="${PRIMARY_PORT:-8080}"
LOG="/var/log/pywork-failover.log"
PRIMARY_IP="${PRIMARY_IP:-}"
FORCE=false

[[ "$1" == "--force" ]] && FORCE=true

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# 检查主机是否可达
check_primary() {
    if [[ -z "$PRIMARY_IP" ]]; then
        log "PRIMARY_IP not set, cannot check primary"
        return 1
    fi
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout 5 --max-time 10 \
        "http://${PRIMARY_IP}:${PRIMARY_PORT}/" 2>/dev/null || echo "000")
    [[ "$http_code" == "200" ]]
}

log "=== Failover started ==="

# 检查主机状态
if [[ "$FORCE" != true ]]; then
    log "Checking primary at $PRIMARY_IP ..."
    if check_primary; then
        log "Primary is alive. Use --force to override."
        exit 0
    fi
    log "Primary is DOWN, proceeding with failover..."
else
    log "Force mode, skipping primary check"
fi

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
INTEGRITY=$(sqlite3 /tmp/failover-restore.db "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
    log "ERROR: Database integrity check failed: $INTEGRITY"
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
log "Running WAL checkpoint..."
sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>&1 | tee -a "$LOG"

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

log "=== Failover complete ==="
log "Remember to update DNS: $PRIMARY_IP → $(hostname -I | awk '{print $1}')"
