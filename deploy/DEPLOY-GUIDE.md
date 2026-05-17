# pyWork 生产环境部署指南（宝塔面板 + Litestream 双机热备）

> 适用场景：新 VPS 已安装宝塔面板，需要部署 pyWork 并配置双机热备

---

## 前置准备

| 项目 | 主机 (VPS-1) | 备机 (VPS-2) |
|------|-------------|-------------|
| 宝塔面板 | 已安装 | 已安装 |
| 域名 | `<DOMAIN>` (DNS A 记录指向主机) | 同一域名（故障切换时改 DNS） |
| IP | `<PRIMARY_IP>` | `<STANDBY_IP>` |
| SSH 端口 | `<SSH_PORT_1>` (宝塔→安全→SSH端口查看) | `<SSH_PORT_2>` |

> **重要**：宝塔可能修改了 SSH 默认端口，部署前务必确认。

---

## 第一部分：主机 (VPS-1) 部署

### 1.1 宝塔面板基础配置

**1) 确认 SSH 端口**

```bash
# 在宝塔终端中执行
grep "^Port " /etc/ssh/sshd_config || echo "默认端口 22"
```

**2) 安装 Python 3.11+**

宝塔面板 →「软件商店」→ 搜索 "Python" → 安装 Python 3.11

或手动安装：
```bash
# Ubuntu 22.04+ 自带 Python 3.11
python3 --version
# 如果版本不够，安装 deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
```

**3) 放行防火墙端口**

宝塔面板 →「安全」→「防火墙」→ 放行：

| 端口 | 用途 |
|------|------|
| `80` | HTTP |
| `443` | HTTPS（如启用） |
| `8080` | pyWork 内部端口（仅 Nginx 转发用，可不放行外网） |

---

### 1.2 创建 pyWork 用户和目录

```bash
# 创建系统用户
sudo useradd -r -s /bin/false pywork

# 创建目录（宝塔环境路径）
sudo mkdir -p /www/wwwroot/pywork /www/wwwroot/pywork/data
sudo chown pywork:pywork /www/wwwroot/pywork /www/wwwroot/pywork/data
```

---

### 1.3 下载并安装 pyWork

```bash
cd /www/wwwroot/pywork

# 克隆代码（替换为你的仓库地址）
sudo -u pywork git clone https://github.com/tojoevan/pywork.git .

# 创建虚拟环境
sudo -u pywork python3.11 -m venv .venv

# 安装依赖
sudo -u pywork .venv/bin/pip install -e .
```

验证安装：
```bash
sudo -u pywork .venv/bin/pywork --help
```

---

### 1.4 配置 pyWork 环境变量

创建 `.env` 文件：
```bash
sudo -u pywork tee /www/wwwroot/pywork/.env << 'EOF'
# pyWork 配置
HOST=127.0.0.1
PORT=8080
DATA_DIR=/www/wwwroot/pywork/data
SECRET_KEY=$(openssl rand -hex 32)
EOF
```

---

### 1.5 创建 pyWork systemd 服务

```bash
sudo tee /etc/systemd/system/pywork.service << 'EOF'
[Unit]
Description=pyWork Digital Workbench
After=network.target

[Service]
Type=simple
User=pywork
Group=pywork
WorkingDirectory=/www/wwwroot/pywork
ExecStart=/www/wwwroot/pywork/.venv/bin/pywork
Restart=always
RestartSec=5
Environment=PATH=/www/wwwroot/pywork/.venv/bin:/usr/local/bin:/usr/bin:/bin

# 安全加固
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/www/wwwroot/pywork/data

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pywork
sudo systemctl start pywork

# 检查状态
sudo systemctl status pywork
```

验证服务运行：
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/
# 应返回 200
```

---

### 1.6 宝塔 Nginx 反向代理

**方式 A：宝塔面板（推荐）**

1. 宝塔面板 →「网站」→「添加站点」
   - 域名：`<DOMAIN>`
   - PHP 版本：选择"纯静态"
2. 站点创建后 →「设置」→「反向代理」→「添加反向代理」
   - 代理名称：`pywork`
   - 目标 URL：`http://127.0.0.1:8080`
   - 发送域名：`$host`
3. 点击「配置文件」，在 `location /` 块中添加：
   ```nginx
   proxy_set_header Host $host;
   proxy_set_header X-Real-IP $remote_addr;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header X-Forwarded-Proto $scheme;
   ```

**方式 B：手动配置**

```bash
sudo tee /etc/nginx/sites-available/pywork << 'EOF'
server {
    listen 80;
    server_name <DOMAIN>;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/pywork /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**SSL 证书（可选）**

宝塔面板 →「网站」→ 选择站点 →「设置」→「SSL」→「Let's Encrypt」→ 一键申请

---

### 1.7 验证主机部署

```bash
# 本地测试
curl -s http://127.0.0.1:8080/ | head -5

# 外网测试
curl -s -o /dev/null -w "%{http_code}" http://<DOMAIN>/
# 应返回 200
```

浏览器访问 `http://<DOMAIN>`，确认页面正常显示。

---

## 第二部分：备机 (VPS-2) 部署

### 2.1 宝塔面板基础配置

同主机步骤，确认 SSH 端口并放行防火墙。

---

### 2.2 创建用户和目录

```bash
# 创建 litestream 用户（用于接收 WAL）
sudo useradd -r -s /bin/bash -m -d /home/litestream litestream
sudo mkdir -p /home/litestream/.ssh
sudo chmod 700 /home/litestream/.ssh
sudo touch /home/litestream/.ssh/authorized_keys
sudo chmod 600 /home/litestream/.ssh/authorized_keys
sudo chown -R litestream:litestream /home/litestream/.ssh

# 创建 pyWork 用户和目录
sudo useradd -r -s /bin/false pywork
sudo mkdir -p /www/wwwroot/pywork /www/wwwroot/pywork/data
sudo chown pywork:pywork /www/wwwroot/pywork /www/wwwroot/pywork/data
```

---

### 2.3 下载 pyWork 代码（不启动）

```bash
cd /www/wwwroot/pywork
sudo -u pywork git clone https://github.com/tojoevan/pywork.git .
sudo -u pywork python3.11 -m venv .venv
sudo -u pywork .venv/bin/pip install -e .
```

---

### 2.4 创建 pyWork systemd 服务（不启动）

```bash
sudo tee /etc/systemd/system/pywork.service << 'EOF'
[Unit]
Description=pyWork Digital Workbench (Standby)
After=network.target

[Service]
Type=simple
User=pywork
Group=pywork
WorkingDirectory=/www/wwwroot/pywork
ExecStart=/www/wwwroot/pywork/.venv/bin/pywork
Restart=always
RestartSec=5
Environment=PATH=/www/wwwroot/pywork/.venv/bin:/usr/local/bin:/usr/bin:/bin

NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/www/wwwroot/pywork/data

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
# 注意：不要 start，等故障切换时再启动
```

---

### 2.5 宝塔 Nginx 反向代理（备机）

同主机步骤，添加站点 `<DOMAIN>`，反向代理指向 `http://127.0.0.1:8080`。

备机 pyWork 未启动时，访问会返回 502，这是正常的。

---

## 第三部分：Litestream 双机热备配置

### 3.1 主机安装 Litestream

```bash
LITESTREAM_VERSION="0.5.11"
wget https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.deb
sudo dpkg -i litestream-${LITESTREAM_VERSION}-linux-x86_64.deb
litestream version
```

---

### 3.2 主机生成 SSH 密钥

```bash
sudo mkdir -p /home/pywork/.ssh
sudo ssh-keygen -t ed25519 -f /home/pywork/.ssh/litestream_key -N "" -C "litestream@vps-primary"
sudo chmod 600 /home/pywork/.ssh/litestream_key
sudo chown -R pywork:pywork /home/pywork/.ssh

# 显示公钥（复制到备机）
cat /home/pywork/.ssh/litestream_key.pub
```

---

### 3.3 备机添加公钥

将上一步的公钥内容添加到备机：

```bash
# 在备机上执行，替换 <PUBLIC_KEY> 为主机公钥
echo "<PUBLIC_KEY>" | sudo tee -a /home/litestream/.ssh/authorized_keys
sudo chown litestream:litestream /home/litestream/.ssh/authorized_keys
```

---

### 3.4 主机配置 Litestream

```bash
sudo tee /etc/litestream.yml << 'EOF'
dbs:
  - path: /www/wwwroot/pywork/data/pywork.db
    monitor-interval: 1s
    checkpoint-interval: 1m
    replica:
      type: sftp
      host: <STANDBY_IP>:<SSH_PORT_2>
      user: litestream
      key-path: /home/pywork/.ssh/litestream_key
      path: /www/wwwroot/pywork/data/pywork.db
      sync-interval: 1s
      concurrent-writes: true

logging:
  level: info
  type: text
  stderr: true
EOF
```

---

### 3.5 测试 Litestream 连接

```bash
# 手动运行测试（Ctrl+C 停止）
sudo litestream replicate -config /etc/litestream.yml

# 看到类似输出表示成功：
# replicated: /www/wwwroot/pywork/data/pywork.db (xxx bytes)
```

验证备机收到文件：
```bash
# 在备机上检查
ls -la /www/wwwroot/pywork/data/
# 会看到 pywork.db 是一个目录（不是文件），里面有 ltx/ 子目录
# 这是 Litestream v0.4+ 的正常行为：SFTP replica 以 LTX 日志目录形式存储
ls -la /www/wwwroot/pywork/data/pywork.db/ltx/
```

> **重要说明**：备机的 `pywork.db` 是一个 **目录**，包含 Litestream 的 LTX 事务日志。
> 它不是可直接使用的 SQLite 数据库文件。故障切换时必须先执行 `litestream restore`
> 将 LTX 日志合并为实际的 `.db` 文件（见第五部分）。

---

### 3.6 主机设置 Litestream systemd 服务

```bash
sudo tee /etc/systemd/system/litestream.service << 'EOF'
[Unit]
Description=Litestream SQLite Replication
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/litestream replicate -config /etc/litestream.yml
Restart=always
RestartSec=5
User=root
Group=root

NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/www/wwwroot/pywork/data /home/pywork/.ssh

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable litestream
sudo systemctl start litestream

# 检查状态
sudo systemctl status litestream
sudo journalctl -u litestream -f
```

---

### 3.7 备机安装 Litestream（用于 restore）

备机不需要运行持续的 Litestream 服务，但需要安装 `litestream` 命令行工具，
以便在故障切换时执行 `restore` 将 LTX 目录转换为可用的 SQLite 数据库。

```bash
# 在备机上安装 Litestream（与主机相同版本）
LITESTREAM_VERSION="0.5.11"
wget https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.deb
sudo dpkg -i litestream-${LITESTREAM_VERSION}-linux-x86_64.deb
litestream version
```

**备机 Litestream 配置**（仅用于 restore，不是常驻服务）：

```bash
sudo tee /etc/litestream.yml << 'EOF'
dbs:
  - path: /www/wwwroot/pywork/data/pywork.db
    replica:
      type: sftp
      host: localhost
      user: litestream
      key-path: /home/litestream/.ssh/litestream_key
      path: /www/wwwroot/pywork/data/pywork.db

logging:
  level: info
  type: text
  stderr: true
EOF
```

> 注意：此配置仅在故障切换时手动执行 `litestream restore` 使用，不需要创建 systemd 服务。

---

## 第四部分：健康检查与监控

### 4.1 主机健康检查脚本

```bash
sudo tee /www/wwwroot/pywork/scripts/health-check.sh << 'SCRIPT'
#!/bin/bash
PYWORK_URL="http://localhost:8080/"
LITESTREAM_SERVICE="litestream"
LOG="/var/log/pywork-health.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PYWORK_URL" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" != "200" ]]; then
    log "ALERT: pyWork DOWN (HTTP $HTTP_CODE)"
fi

if ! systemctl is-active --quiet "$LITESTREAM_SERVICE"; then
    log "ALERT: Litestream DOWN"
fi
SCRIPT

sudo chmod +x /www/wwwroot/pywork/scripts/health-check.sh
```

**添加 crontab：**
```bash
sudo crontab -e
# 添加：
# * * * * * /www/wwwroot/pywork/scripts/health-check.sh
```

---

### 4.2 备机数据库新鲜度检查

> 注意：备机的 `pywork.db` 是 Litestream LTX 日志目录，不是单个文件。
> 新鲜度检查应基于 LTX 目录中最新文件的时间戳。

```bash
sudo tee /www/wwwroot/pywork/scripts/standby-check.sh << 'SCRIPT'
#!/bin/bash
LTX_DIR="/www/wwwroot/pywork/data/pywork.db/ltx"
MAX_AGE=300
LOG="/var/log/pywork-standby.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

if [[ ! -d "$LTX_DIR" ]]; then
    log "ALERT: LTX directory not found: $LTX_DIR"
    exit 1
fi

# 获取最新 LTX 文件的修改时间
LAST_MOD=$(find "$LTX_DIR" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
if [[ -z "$LAST_MOD" ]]; then
    log "ALERT: No LTX files found in $LTX_DIR"
    exit 1
fi

NOW=$(date +%s)
AGE=$((NOW - LAST_MOD))

if [[ "$AGE" -gt "$MAX_AGE" ]]; then
    log "ALERT: Standby LTX data is ${AGE}s old (max ${MAX_AGE}s)"
fi
SCRIPT

sudo chmod +x /www/wwwroot/pywork/scripts/standby-check.sh
sudo crontab -e
# 添加：
# */5 * * * * /www/wwwroot/pywork/scripts/standby-check.sh
```

---

## 第五部分：故障切换演练

### 5.1 手动切换流程（在备机上执行）

> 备机通过 rsync 定时从主机拉取 SQLite 数据库备份到 `pywork.db-replica`。
> 故障切换时直接使用该备份文件启动 pyWork。

```bash
# 1. 验证备份文件完整性
sqlite3 /www/wwwroot/pywork/data/pywork.db-replica "PRAGMA integrity_check;"
# 应返回 ok

# 2. 替换数据库文件
sudo rm -f /www/wwwroot/pywork/data/pywork.db
sudo cp /www/wwwroot/pywork/data/pywork.db-replica /www/wwwroot/pywork/data/pywork.db
sudo chown pywork:pywork /www/wwwroot/pywork/data/pywork.db

# 3. WAL checkpoint
sqlite3 /www/wwwroot/pywork/data/pywork.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 4. 启动 pyWork
sudo systemctl start pywork

# 5. 验证
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/
# 应返回 200

# 6. 切换 DNS
# 将 A 记录从 <PRIMARY_IP> 改为 <STANDBY_IP>
```

### 5.2 使用故障切换脚本

```bash
# 设置环境变量
export PRIMARY_IP="<PRIMARY_IP>"
export DB_PATH="/www/wwwroot/pywork/data/pywork.db"
export BACKUP_PATH="/www/wwwroot/pywork/data/pywork.db-replica"

# 执行切换（自动验证 + 启动）
sudo -E /www/wwwroot/pywork/scripts/failover.sh

# 强制切换（跳过主机检查）
sudo -E /www/wwwroot/pywork/scripts/failover.sh --force
```

### 5.3 自动故障检测与切换（推荐）

在备机上部署 `pywork-failover-watchdog` 服务，自动检测主机宕机并执行切换。

**原理**：
- 每 10 秒向主机 pyWork 发送 HTTP 请求
- 连续 3 次失败（约 30 秒）判定主机宕机
- 自动验证备份完整性 + 复制 + 启动 pyWork
- DNS 需手动切换（避免脑裂）

**部署步骤**：

```bash
# 1. 编辑服务文件，设置 PRIMARY_IP
sudo vim /etc/systemd/system/pywork-failover-watchdog.service
# 修改: Environment=PRIMARY_IP=<你的主机IP>

# 2. 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable --now pywork-failover-watchdog

# 3. 检查状态
sudo systemctl status pywork-failover-watchdog
sudo journalctl -u pywork-failover-watchdog -f
```

**环境变量配置**（在 service 文件中修改）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PRIMARY_IP` | (必填) | 主机 IP |
| `PRIMARY_PORT` | `8080` | 主机 pyWork 端口 |
| `DB_PATH` | `/www/wwwroot/pywork/data/pywork.db` | 数据库路径 |
| `BACKUP_PATH` | `/www/wwwroot/pywork/data/pywork.db-replica` | rsync 备份文件路径 |
| `CHECK_INTERVAL` | `10` | 检测间隔（秒） |
| `MAX_FAILURES` | `3` | 连续失败次数阈值 |

**切换后操作**：
1. 确认备机 pyWork 正常访问
2. 手动切换 DNS A 记录
3. 排查主机故障原因
4. 主机恢复后，重新配置为主机，备机重新部署 watchdog

### 5.4 Gist 仲裁防脑裂（推荐）

> 解决双主/双备问题：用 GitHub Gist 作为共享状态存储，两个节点通过读写 Gist 协调角色。

**原理**：
- 每个节点每 10 秒向 Gist 写入自己的心跳和角色
- 读取对方状态后做角色决策
- 双 primary 冲突时，`promoted_at` 早的赢
- 网络不通时自动降级为 standby（安全优先）

**一次性初始化**（在任意一台机器上执行）：

```bash
# 1. 创建 GitHub Personal Access Token
#    GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
#    权限：Gists → Read and write

# 2. 安装 jq
apt install jq

# 3. 运行初始化脚本
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"
export NODE1_ID="vps1"  # 主机标识
export NODE2_ID="vps2"  # 备机标识
/www/wwwroot/pywork/scripts/setup-gist-arbitrator.sh

# 记录输出的 GIST_ID
```

**部署到两台机器**：

```bash
# 复制服务文件
cp /www/wwwroot/pywork/deploy/pywork-role-manager.service /etc/systemd/system/

# 编辑，填入 GIST_ID 和 GITHUB_TOKEN
vim /etc/systemd/system/pywork-role-manager.service

# 启用（两台都执行）
systemctl daemon-reload
systemctl enable --now pywork-role-manager

# 查看日志
journalctl -u pywork-role-manager -f
```

**环境变量配置**：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NODE_ID` | hostname | 本节点标识（主机和备机不同） |
| `GIST_ID` | (必填) | GitHub Gist ID |
| `GITHUB_TOKEN` | (必填) | GitHub Token |
| `HEARTBEAT_INTERVAL` | `10` | 心跳间隔（秒） |
| `HEARTBEAT_TIMEOUT` | `30` | 心跳超时（秒） |
| `ROLE_FILE` | `/etc/pywork-role` | 角色状态文件 |

**工作流程**：
```
启动 → 写入 standby 状态 → 每 10 秒循环:
  读对方状态 → 决策角色 → 写入自己的状态 → 启停 pyWork
```

**故障场景处理**：
- 主机宕机：备机检测到对方心跳超时 → 升级为 primary → 启动 pyWork
- 网络分区：两节点都连不上 Gist → 都降级为 standby（宁停不脑裂）
- 双 primary：比较 `promoted_at`，早的赢，晚的降级
- 主机恢复：检测到备机已是 primary → 自动降级为 standby

---

## 部署检查清单

### 主机 (VPS-1)
- [ ] 宝塔面板 SSH 端口已确认
- [ ] 防火墙放行 80、443 端口
- [ ] Python 3.11+ 已安装
- [ ] pyWork 代码已克隆
- [ ] 虚拟环境已创建，依赖已安装
- [ ] systemd 服务已创建并启动
- [ ] Nginx 反向代理已配置
- [ ] SSL 证书已申请（可选）
- [ ] 外网访问正常
- [ ] Litestream 已安装
- [ ] SSH 密钥已生成
- [ ] Litestream 配置已写入 `/etc/litestream.yml`
- [ ] Litestream systemd 服务已启动
- [ ] 健康检查脚本已部署

### 备机 (VPS-2)
- [ ] 宝塔面板 SSH 端口已确认
- [ ] 防火墙放行 80、443 端口
- [ ] litestream 用户已创建
- [ ] SSH 目录和公钥已配置
- [ ] pyWork 代码已克隆（不启动）
- [ ] systemd 服务已创建（不启动）
- [ ] Nginx 反向代理已配置
- [ ] Litestream 已安装（用于 restore，非常驻服务）
- [ ] `/etc/litestream.yml` 已配置（restore 用）
- [ ] 数据库新鲜度检查脚本已部署
- [ ] 确认 `pywork.db-replica` 为 LTX 目录（`ls /www/wwwroot/pywork/data/pywork.db-replica/ltx/`）
- [ ] Failover watchdog 服务已配置并启用（`PRIMARY_IP` 已设置）

### 验证
- [ ] 主机写入测试数据，备机 replica 目录 1 秒内出现新文件
  ```bash
  # 主机写入测试
  curl -X POST http://localhost:8080/api/... -d 'test'
  # 备机检查 replica 目录变化
  watch -n 1 'ls -lt /www/wwwroot/pywork/data/pywork.db-replica/ltx/ | head -5'
  ```
- [ ] 手动 restore 测试：`litestream restore -o /tmp/test.db file:///www/wwwroot/pywork/data/pywork.db-replica`
- [ ] 故障切换演练：停止主机 pyWork，备机 watchdog 30 秒内自动切换
- [ ] 故障切换后 pyWork 正常启动并可访问
- [ ] DNS 切换流程已演练
- [ ] 监控告警已配置

---

## 关键文件位置

| 文件 | 主机位置 | 备机位置 |
|------|---------|---------|
| pyWork 代码 | `/www/wwwroot/pywork/` | `/www/wwwroot/pywork/` |
| SQLite 数据库 | `/www/wwwroot/pywork/data/pywork.db`（单个文件） | `/www/wwwroot/pywork/data/pywork.db/`（LTX 目录，故障切换时 restore 为文件） |
| Litestream 配置 | `/etc/litestream.yml` | `/etc/litestream.yml`（仅 restore 用） |
| SSH 密钥 | `/home/pywork/.ssh/litestream_key` | `/home/litestream/.ssh/authorized_keys` |
| systemd 服务 | `/etc/systemd/system/pywork.service` | `/etc/systemd/system/pywork.service` |
| systemd 服务 | `/etc/systemd/system/litestream.service` | — |
| 健康检查 | `/www/wwwroot/pywork/scripts/health-check.sh` | — |
| 新鲜度检查 | — | `/www/wwwroot/pywork/scripts/standby-check.sh` |
| 故障切换 | — | `/www/wwwroot/pywork/scripts/failover.sh` |
| 自动切换 watchdog | — | `/www/wwwroot/pywork/scripts/failover-watchdog.sh` |
| systemd 服务 | — | `/etc/systemd/system/pywork-failover-watchdog.service` |

---

## 常见问题

### Q: 宝塔 SSH 端口不是 22 怎么办？
Litestream 配置中 `host` 字段使用实际端口：`<STANDBY_IP>:2222`

### Q: 备机访问返回 502？
正常。备机 pyWork 未启动，Nginx 反向代理找不到后端服务。故障切换后会恢复。

### Q: Litestream 连接失败？
检查：
1. 备机 SSH 端口是否正确
2. 备机防火墙是否放行 SSH 端口
3. 公钥是否正确添加到 `authorized_keys`
4. 手动测试：`ssh -i /home/pywork/.ssh/litestream_key litestream@<STANDBY_IP>`

### Q: 如何回退到主机？
1. 备机停止 pyWork：`sudo systemctl stop pywork`
2. 主机启动 Litestream：`sudo systemctl start litestream`
3. 主机启动 pyWork：`sudo systemctl start pywork`
4. DNS 切回主机 IP

### Q: 备机的 pywork.db 是目录不是文件？
正常。Litestream v0.4+ 的 SFTP replica 以 LTX 日志目录形式存储。
故障切换时执行 `litestream restore` 即可重建为单个 SQLite 文件。
不要手动将目录当作数据库使用，否则 pyWork 会启动失败。

### Q: litestream restore 失败怎么办？
1. 检查 replica 目录是否有文件：`ls -la /www/wwwroot/pywork/data/pywork.db-replica/ltx/`
2. 如果本地 restore 失败，从主机直接 SCP 复制数据库文件
3. 如果完全无法恢复，联系管理员从备份恢复

### Q: Watchdog 误触发了怎么办？
如果主机只是短暂网络抖动，watchdog 已经切换了：
1. 停止备机 pyWork：`systemctl stop pywork`
2. 恢复主机服务：`systemctl start litestream && systemctl start pywork`
3. 重新初始化备机 replica 目录
4. 重启 watchdog：`systemctl restart pywork-failover-watchdog`

### Q: 如何调整 watchdog 灵敏度？
编辑 `/etc/systemd/system/jiao`：
- `CHECK_INTERVAL=10` → 检测间隔（秒）
- `MAX_FAILURES=3` → 连续失败次数（3 次 × 10 秒 = 30 秒触发）
修改后执行 `systemctl daemon-reload && systemctl restart pywork-failover-watchdog`
