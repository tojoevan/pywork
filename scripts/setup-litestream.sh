#!/bin/bash
# Litestream 部署初始化脚本
# 在主机和备机上分别运行，自动完成安装和配置
#
# 用法:
#   主机: ./setup-litestream.sh primary
#   备机: ./setup-litestream.sh standby
set -e

ROLE="$1"
LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.5.0}"
DB_PATH="${PYWORK_DB_PATH:-/data/pywork/pywork.db}"
DB_DIR=$(dirname "$DB_PATH")

if [[ "$ROLE" != "primary" && "$ROLE" != "standby" ]]; then
    echo "用法: $0 primary|standby"
    echo "  primary - 主机：安装 Litestream + 配置推送"
    echo "  standby - 备机：创建用户 + 目录 + 安装 Litestream"
    exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# === 公共步骤：安装 Litestream ===
install_litestream() {
    if command -v litestream &>/dev/null; then
        log "Litestream already installed: $(litestream version)"
        return
    fi
    log "Installing Litestream v${LITESTREAM_VERSION}..."
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
    esac
    local deb="litestream-v${LITESTREAM_VERSION}-linux-${arch}.deb"
    wget -q "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/${deb}" -O "/tmp/${deb}"
    dpkg -i "/tmp/${deb}"
    rm -f "/tmp/${deb}"
    log "Litestream installed: $(litestream version)"
}

# === 主机配置 ===
setup_primary() {
    log "=== Setting up PRIMARY ==="

    install_litestream

    # 创建数据目录
    mkdir -p "$DB_DIR"
    log "Data directory: $DB_DIR"

    # 生成 SSH 密钥（如果不存在）
    local key="/home/pywork/.ssh/litestream_key"
    if [[ ! -f "$key" ]]; then
        mkdir -p /home/pywork/.ssh
        ssh-keygen -t ed25519 -f "$key" -N "" -C "litestream@$(hostname)"
        chmod 600 "$key"
        log "SSH key generated: $key"
        log "PUBLIC KEY (add to standby's authorized_keys):"
        cat "${key}.pub"
    else
        log "SSH key already exists: $key"
    fi

    # 安装 systemd 服务
    log "Installing systemd service..."
    cp "$(dirname "$0")/../deploy/litestream.service" /etc/systemd/system/litestream.service
    sed -i "s|<PRIMARY_DB_DIR>|$DB_DIR|g" /etc/systemd/system/litestream.service
    systemctl daemon-reload
    log "Service installed. Configure /etc/litestream.yml then run:"
    log "  systemctl enable --now litestream"

    log "=== Primary setup complete ==="
    log "Next steps:"
    log "  1. Copy deploy/litestream.yml to /etc/litestream.yml"
    log "  2. Edit /etc/litestream.yml with standby IP and SSH port"
    log "  3. Copy SSH public key to standby"
    log "  4. systemctl enable --now litestream"
}

# === 备机配置 ===
setup_standby() {
    log "=== Setting up STANDBY ==="

    install_litestream

    # 创建 litestream 用户
    if ! id litestream &>/dev/null; then
        useradd -r -s /bin/bash -m -d /home/litestream litestream
        log "User 'litestream' created"
    else
        log "User 'litestream' already exists"
    fi

    # 创建数据目录
    mkdir -p "$DB_DIR"
    chown litestream:litestream "$DB_DIR"
    log "Data directory: $DB_DIR"

    # 配置 SSH
    mkdir -p /home/litestream/.ssh
    chmod 700 /home/litestream/.ssh
    touch /home/litestream/.ssh/authorized_keys
    chmod 600 /home/litestream/.ssh/authorized_keys
    chown -R litestream:litestream /home/litestream/.ssh
    log "SSH directory configured"

    log "=== Standby setup complete ==="
    log "Next steps:"
    log "  1. Add primary's public key to /home/litestream/.ssh/authorized_keys"
    log "  2. Install pyWork code (do not start)"
    log "  3. Configure Nginx reverse proxy to 127.0.0.1:8080"
    log "  4. Test: ssh litestream@<STANDBY_IP> from primary"
}

case "$ROLE" in
    primary) setup_primary ;;
    standby) setup_standby ;;
esac
