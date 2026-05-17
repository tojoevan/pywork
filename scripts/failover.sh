#!/bin/bash
# 故障切换脚本 - 在备机上运行
# 用法: ./failover.sh [--force]
# --force: 跳过主机可达性检查，直接执行切换
set -e

DB_PATH="${PYWORK_DB_PATH:-/data/pywork/pywork.db}"
PYWORK_SERVICE="${PYWORK_SERVICE:-pywork}"
LITESTREAM_SERVICE="${LITESTREAM_SERVICE:-litestream-restore}"
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
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        -i /home/litestream/.ssh/litestream_key \
        litestream@"$PRIMARY_IP" "echo ok" 2>/dev/null
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

# 1. 停止 Litestream restore
log "Stopping Litestream restore..."
systemctl stop "$LITESTREAM_SERVICE" 2>/dev/null || true

# 2. 检查数据库完整性
log "Checking database integrity..."
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
    log "ERROR: Database integrity check failed: $INTEGRITY"
    exit 1
fi
log "Database integrity: OK"

# 3. WAL checkpoint
log "Running WAL checkpoint..."
sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>&1 | tee -a "$LOG"

# 4. 启动 pyWork
log "Starting pyWork..."
systemctl start "$PYWORK_SERVICE"

# 5. 验证启动
sleep 2
if systemctl is-active --quiet "$PYWORK_SERVICE"; then
    log "pyWork is running"
else
    log "ERROR: pyWork failed to start"
    journalctl -u "$PYWORK_SERVICE" -n 20 --no-pager >> "$LOG"
    exit 1
fi

log "=== Failover complete ==="
log "Remember to update DNS: $PRIMARY_IP → $(hostname -I | awk '{print $1}')"
