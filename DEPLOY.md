# pyWork 部署文档

> **版本**: 0.1.0  
> **更新时间**: 2026-04-17  
> **适用平台**: macOS / Linux / Windows

---

## 目录

1. [环境要求](#环境要求)
2. [快速开始](#快速开始)
3. [安装步骤](#安装步骤)
4. [配置说明](#配置说明)
5. [启动方式](#启动方式)
6. [MCP 集成](#mcp-集成)
7. [生产部署](#生产部署)
8. [常见问题](#常见问题)

---

## 环境要求

### 必需

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.11 | 推荐使用 3.11+ |
| pip | 最新版 | Python 包管理器 |

### 硬件建议

| 场景 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 开发/测试 | 1 核 | 512MB | 100MB |
| 生产环境 | 2 核+ | 1GB+ | 1GB+ |

---

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> pyWork
cd pyWork

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -e .

# 4. 启动服务
pywork --http --port 8080
```

访问 http://localhost:8080 验证服务运行。

---

## 安装步骤

### 方式一：开发模式安装（推荐）

```bash
# 克隆项目
git clone <repo-url> pyWork
cd pyWork

# 创建并激活虚拟环境
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat

# 安装项目（开发模式）
pip install -e .

# 安装开发依赖（可选）
pip install -e ".[dev]"
```

### 方式二：pip 安装

```bash
pip install pywork
```

### 验证安装

```bash
# 检查命令
pywork --help

# 运行测试
pytest tests/
```

---

## 配置说明

### 命令行参数

```bash
pywork [选项]

选项:
  --db <path>          数据库路径 (默认: ./data/pywork.db)
  --plugins <dir>      插件目录 (默认: ./plugins)
  --enabled <list>     启用的插件，逗号分隔 (默认: blog)
  --http               启动 HTTP 服务器
  --mcp-stdio          启动 MCP stdio 服务
  --host <host>        HTTP 监听地址 (默认: 0.0.0.0)
  --port <port>        HTTP 端口 (默认: 8080)
```

### 环境变量

```bash
# 数据库路径
export PYWORK_DB=/data/pywork.db

# 插件目录
export PYWORK_PLUGINS=/opt/pywork/plugins

# 启用的插件
export PYWORK_ENABLED=blog,notes,todo
```

### 配置文件（计划中）

未来将支持 `pywork.toml` 配置文件：

```toml
[server]
host = "0.0.0.0"
port = 8080

[storage]
path = "/data/pywork.db"

[plugins]
enabled = ["blog", "notes", "todo"]
directory = "./plugins"
```

---

## 启动方式

### HTTP 服务模式

```bash
# 前台运行
pywork --http --port 8080

# 指定数据库和插件
pywork --http --db /data/pywork.db --enabled blog,notes

# 输出示例
# ✓ SQLite engine started: /data/pywork.db
# ✓ Plugins loaded: ['blog']
# INFO:     Started server process [12345]
# INFO:     Uvicorn running on http://0.0.0.0:8080
```

### MCP stdio 模式

用于 AI 助手集成（如 Claude Desktop、Cursor）：

```bash
pywork --mcp-stdio
```

配置 Claude Desktop：

```json
{
  "mcpServers": {
    "pywork": {
      "command": "/path/to/pyWork/.venv/bin/python",
      "args": ["-m", "app.main", "--mcp-stdio"],
      "cwd": "/path/to/pyWork"
    }
  }
}
```

### 后台运行

```bash
# nohup 后台运行
nohup pywork --http --port 8080 > pywork.log 2>&1 &

# systemd 服务（推荐）
# 见下方生产部署章节
```

---

## MCP 集成

### 可用工具

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `blog.create_post` | 创建文章 | title, content, status?, tags? |
| `blog.search_posts` | 搜索文章 | status?, tags?, limit? |
| `blog.update_post` | 更新文章 | id, title?, content?, status? |
| `blog.delete_post` | 删除文章 | id |

### 可用资源

| 资源 URI | 说明 |
|----------|------|
| `blog://posts` | 所有文章列表 |
| `blog://posts/{id}` | 单篇文章详情 |

### 可用提示模板

| 模板名 | 说明 |
|--------|------|
| `blog.blog-writing-template` | 博客写作模板 |

### AI 助手集成示例

**Cursor 编辑器配置** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "pywork": {
      "command": "python",
      "args": ["-m", "app.main", "--mcp-stdio"],
      "cwd": "/path/to/pyWork"
    }
  }
}
```

**Claude Desktop 配置**:

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
或 `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "pywork": {
      "command": "/path/to/pyWork/.venv/bin/python",
      "args": ["-m", "app.main", "--mcp-stdio"],
      "cwd": "/path/to/pyWork"
    }
  }
}
```

---

## 生产部署

### systemd 服务（Linux 推荐）

创建服务文件 `/etc/systemd/system/pywork.service`:

```ini
[Unit]
Description=pyWork Digital Workbench
After=network.target

[Service]
Type=simple
User=pywork
Group=pywork
WorkingDirectory=/opt/pywork
Environment="PATH=/opt/pywork/.venv/bin"
ExecStart=/opt/pywork/.venv/bin/pywork --http --port 8080 --db /data/pywork.db
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
# 创建用户
sudo useradd -r -s /bin/false pywork

# 创建目录
sudo mkdir -p /opt/pywork /data
sudo chown pywork:pywork /opt/pywork /data

# 部署代码
sudo -u pywork git clone <repo-url> /opt/pywork
cd /opt/pywork
sudo -u pywork python3 -m venv .venv
sudo -u pywork .venv/bin/pip install -e .

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable pywork
sudo systemctl start pywork

# 查看状态
sudo systemctl status pywork
```

### Docker 部署

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn aiosqlite jinja2 pydantic mcp

# 复制代码
COPY app/ ./app/
COPY plugins/ ./plugins/

# 创建数据目录
RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "-m", "app.main", "--http", "--port", "8080", "--db", "/data/pywork.db"]
```

**构建和运行**:

```bash
# 构建镜像
docker build -t pywork:latest .

# 运行容器
docker run -d \
  --name pywork \
  -p 8080:8080 \
  -v pywork-data:/data \
  pywork:latest
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name pywork.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 安全建议

1. **使用 HTTPS**：配置 SSL 证书（Let's Encrypt）
2. **限制访问**：使用防火墙限制端口访问
3. **定期备份**：备份 SQLite 数据库文件
4. **日志监控**：配置日志轮转和监控

---

## 常见问题

### Q: 端口被占用怎么办？

```bash
# 查找占用进程
lsof -i :8080

# 杀掉进程
kill -9 <PID>

# 或使用其他端口
pywork --http --port 8081
```

### Q: 数据库文件在哪里？

默认位置 `./data/pywork.db`，可通过 `--db` 参数指定：

```bash
pywork --db /path/to/custom.db
```

### Q: 如何添加新插件？

1. 在 `plugins/` 目录创建插件包
2. 实现 `Plugin` 接口（见 `app/plugin/interface.py`）
3. 启动时指定插件名：

```bash
pywork --enabled blog,myplugin
```

### Q: 如何备份数据？

```bash
# SQLite 在线备份
sqlite3 /data/pywork.db ".backup /backup/pywork.db"

# 或直接复制
cp /data/pywork.db /backup/pywork_$(date +%Y%m%d).db
```

### Q: MCP 连接失败？

检查：
1. Python 路径是否正确
2. 工作目录是否正确
3. 虚拟环境是否激活
4. 查看 AI 助手的 MCP 日志

### Q: 内存占用过高？

1. 检查是否有内存泄漏
2. 减少启用的插件数量
3. 限制 uvicorn workers 数量

---

## API 参考

### 系统接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 系统状态 |
| GET | `/health` | 健康检查 |

### 博客接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/blog/posts` | 创建文章 |
| GET | `/blog/posts` | 列出文章 |
| GET | `/blog/posts/{id}` | 获取文章 |
| PUT | `/blog/posts/{id}` | 更新文章 |
| DELETE | `/blog/posts/{id}` | 删除文章 |
| GET | `/blog/search` | 搜索文章 |

### 请求/响应示例

**创建文章**:

```bash
POST /blog/posts
Content-Type: application/json

{
  "title": "我的第一篇文章",
  "content": "文章内容...",
  "status": "published",
  "tags": ["测试", "首发"]
}

# 响应
{
  "id": 1,
  "title": "我的第一篇文章",
  "status": "published",
  "created_at": 1713187200
}
```

**搜索文章**:

```bash
GET /blog/search?status=published&limit=10

# 响应
[
  {
    "id": 1,
    "title": "我的第一篇文章",
    "status": "published",
    "created_at": 1713187200
  }
]
```

---

## 更新日志

### v0.1.0 (2026-04-17)

- 初始版本
- 博客插件（CRUD + 搜索）
- MCP Tools/Resources/Prompts 支持
- SQLite 存储引擎
- FastAPI HTTP 服务

---

## 许可证

MIT License

---

## 支持

- 问题反馈: <repo-url>/issues
- 文档: <repo-url>/wiki
