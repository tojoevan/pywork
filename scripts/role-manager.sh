#!/bin/bash
# 角色管理器 - 基于 GitHub Gist 的分布式仲裁
# 每个节点独立运行，通过读写共享 Gist 协调主备角色
#
# 防脑裂策略：
#   1. 两个节点各自写自己的状态文件到同一个 Gist
#   2. 角色决策基于对方心跳 + 自己的状态
#   3. 网络不通时自动降级为 standby（安全优先）
#
# 环境变量:
#   NODE_ID           本节点标识 (默认 hostname)
#   GIST_ID           GitHub Gist ID (必填)
#   GITHUB_TOKEN      GitHub Personal Access Token (必填)
#   PYWORK_PORT       pyWork 端口 (默认 8080)
#   HEARTBEAT_INTERVAL 心跳间隔秒数 (默认 10)
#   HEARTBEAT_TIMEOUT  心跳超时秒数 (默认 30)
#   ROLE_FILE          角色状态文件 (默认 /etc/pywork-role)
#   PYWORK_SERVICE     pyWork 服务名 (默认 pywork)

NODE_ID="${NODE_ID:-$(hostname)}"
GIST_ID="${GIST_ID:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
PYWORK_PORT="${PYWORK_PORT:-8080}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-10}"
HEARTBEAT_TIMEOUT="${HEARTBEAT_TIMEOUT:-30}"
ROLE_FILE="${ROLE_FILE:-/etc/pywork-role}"
PYWORK_SERVICE="${PYWORK_SERVICE:-pywork}"
LOG="/var/log/pywork-role-manager.log"
MY_FILE="${NODE_ID}.json"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# === GitHub Gist API 操作 ===

gist_read() {
    local file="$1"
    curl -s -f -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/gists/$GIST_ID" 2>/dev/null \
        | jq -r ".files.\"$file\".content // empty" 2>/dev/null
}

gist_write() {
    local file="$1"
    local content="$2"
    curl -s -f -X PATCH \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/gists/$GIST_ID" \
        -d "{\"files\":{\"$file\":{\"content\":$content}}}" >/dev/null 2>&1
}

# === 读写节点状态 ===

read_my_state() {
    gist_read "$MY_FILE"
}

read_peer_state() {
    local peer_file="$1"
    gist_read "$peer_file"
}

write_my_state() {
    local role="$1"
    local promoted_at="$2"
    local now
    now=$(date +%s)
    local json
    json=$(jq -nc \
        --arg role "$role" \
        --argjson heartbeat "$now" \
        --argjson promoted_at "${promoted_at:-0}" \
        '{role: $role, heartbeat: $heartbeat, promoted_at: $promoted_at}')
    gist_write "$MY_FILE" "'$json'"
}

# === 角色决策 ===

get_current_role() {
    if [[ -f "$ROLE_FILE" ]]; then
        cat "$ROLE_FILE" 2>/dev/null || echo "standby"
    else
        echo "standby"
    fi
}

set_role() {
    local new_role="$1"
    local old_role
    old_role=$(get_current_role)

    if [[ "$new_role" == "$old_role" ]]; then
        return 0
    fi

    log "Role change: $old_role -> $new_role"
    echo "$new_role" > "$ROLE_FILE"

    case "$new_role" in
        primary)
            log "Starting pyWork as primary..."
            systemctl start "$PYWORK_SERVICE" 2>/dev/null || true
            ;;
        standby)
            log "Stopping pyWork (now standby)..."
            systemctl stop "$PYWORK_SERVICE" 2>/dev/null || true
            ;;
    esac
}

# === 核心决策逻辑 ===

decide_role() {
    local my_state="$1"
    local peer_file="$2"
    local now
    now=$(date +%s)

    # 读取对方状态
    local peer_state
    peer_state=$(read_peer_state "$peer_file")

    local my_role my_heartbeat my_promoted
    my_role=$(echo "$my_state" | jq -r '.role // "standby"')
    my_heartbeat=$(echo "$my_state" | jq -r '.heartbeat // 0')
    my_promoted=$(echo "$my_state" | jq -r '.promoted_at // 0')

    local peer_role peer_heartbeat peer_promoted
    if [[ -n "$peer_state" ]]; then
        peer_role=$(echo "$peer_state" | jq -r '.role // "standby"')
        peer_heartbeat=$(echo "$peer_state" | jq -r '.heartbeat // 0')
        peer_promoted=$(echo "$peer_state" | jq -r '.promoted_at // 0')
    else
        peer_role="standby"
        peer_heartbeat=0
        peer_promoted=0
    fi

    local peer_alive=$(( (now - peer_heartbeat) < HEARTBEAT_TIMEOUT ))

    # 决策逻辑
    if [[ "$peer_alive" -eq 0 && "$my_role" != "primary" ]]; then
        # 对方不在线且我不是 primary → 我成为 primary
        echo "primary|$now"
    elif [[ "$peer_alive" -eq 0 && "$my_role" == "primary" ]]; then
        # 对方不在线且我已是 primary → 保持
        echo "primary|$my_promoted"
    elif [[ "$peer_alive" -eq 1 && "$peer_role" == "primary" && "$my_role" == "primary" ]]; then
        # 双 primary 冲突 → promoted_at 早的赢
        if [[ "$my_promoted" -le "$peer_promoted" ]]; then
            log "Split-brain resolved: I win (my promoted_at=$my_promoted <= peer=$peer_promoted)"
            echo "primary|$my_promoted"
        else
            log "Split-brain resolved: peer wins (my promoted_at=$my_promoted > peer=$peer_promoted)"
            echo "standby|0"
        fi
    elif [[ "$peer_alive" -eq 1 && "$peer_role" == "primary" ]]; then
        # 对方是 primary 且在线 → 我是 standby
        echo "standby|0"
    elif [[ "$peer_alive" -eq 1 && "$my_role" == "primary" ]]; then
        # 我是 primary 且对方在线但不是 primary → 保持
        echo "primary|$my_promoted"
    elif [[ "$peer_alive" -eq 1 && "$peer_role" == "standby" && "$my_role" == "standby" ]]; then
        # 双 standby → 我先升级（通过 promoted_at=0 触发升级）
        # 用 NODE_ID 排序避免同时升级：ID 小的先升级
        local my_id_num peer_id_num
        my_id_num=$(echo "$NODE_ID" | md5sum | cut -c1-8)
        peer_id_num=$(echo "$peer_file" | sed 's/.json//' | md5sum | cut -c1-8)
        if [[ "$my_id_num" < "$peer_id_num" ]]; then
            echo "primary|$now"
        else
            echo "standby|0"
        fi
    else
        # 默认保持当前角色
        echo "$my_role|${my_promoted:-0}"
    fi
}

# === 主循环 ===

if [[ -z "$GIST_ID" || -z "$GITHUB_TOKEN" ]]; then
    echo "ERROR: GIST_ID and GITHUB_TOKEN are required."
    echo "Set them in the service environment or export them."
    exit 1
fi

# 初始化：写入 standby 状态
log "Role manager started: NODE_ID=$NODE_ID, GIST_ID=$GIST_ID"
write_my_state "standby" 0
set_role "standby"

# 获取对方文件名（非 MY_FILE 的另一个 .json 文件）
PEER_FILE=""
for f in $(curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "https://api.github.com/gists/$GIST_ID" 2>/dev/null \
    | jq -r '.files | keys[]' 2>/dev/null); do
    if [[ "$f" != "$MY_FILE" && "$f" == *.json ]]; then
        PEER_FILE="$f"
        break
    fi
done

if [[ -z "$PEER_FILE" ]]; then
    log "WARN: No peer file found in gist. Will detect on next cycle."
fi

while true; do
    # 读取自己当前状态
    my_state=$(read_my_state)
    if [[ -z "$my_state" ]]; then
        log "ERROR: Cannot read my state from gist"
        set_role "standby"
        sleep "$HEARTBEAT_INTERVAL"
        continue
    fi

    # 自动发现对方文件
    if [[ -z "$PEER_FILE" ]]; then
        for f in $(curl -s -H "Authorization: token $GITHUB_TOKEN" \
            "https://api.github.com/gists/$GIST_ID" 2>/dev/null \
            | jq -r '.files | keys[]' 2>/dev/null); do
            if [[ "$f" != "$MY_FILE" && "$f" == *.json ]]; then
                PEER_FILE="$f"
                log "Peer discovered: $PEER_FILE"
                break
            fi
        done
    fi

    # 决策
    if [[ -n "$PEER_FILE" ]]; then
        result=$(decide_role "$my_state" "$PEER_FILE")
        new_role=$(echo "$result" | cut -d'|' -f1)
        promoted_at=$(echo "$result" | cut -d'|' -f2)
    else
        # 没有对方文件，先保持 standby
        new_role="standby"
        promoted_at=0
    fi

    # 写入新状态
    write_my_state "$new_role" "$promoted_at"

    # 应用角色变更
    set_role "$new_role"

    sleep "$HEARTBEAT_INTERVAL"
done
