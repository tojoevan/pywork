# pyWork 部署文档

> **版本**: 0.1.0  
> **更新时间**: 2026-04-19  
> **适用平台**: macOS / Linux

---

## 目录

1. [项目概述](#项目概述)
2. [环境要求](#环境要求)
3. [快速开始](#快速开始)
4. [插件说明](#插件说明)
5. [启动方式](#启动方式)
6. [API 参考](#api-参考)
7. [MCP 集成](#mcp-集成)
8. [生产部署](#生产部署)
9. [常见问题](#常见问题)

---

## 项目概述

pyWork 是一个基于插件架构的多用户数字工作台，使用 Python + FastAPI 构建，SQLite 存储，集成 MCP 协议供 AI 助手调用。

**技术栈**：Python 3.11+ / FastAPI / uvicorn / aiosqlite / Jinja2 / MCP

---

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.11 | 运行时 |
| pip | 最新版 | 包管理器 |

### Python 依赖

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
aiosqlite>=0.19.0
jinja2>=3.1.0
pydantic>=2.5.0
mcp>=1.0.0
markdown>=3.5.0
aiohttp>=3.9.0
Pillow>=10.0.0          # 验证码生成
```

### 硬件建议

| 场景 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 开发/测试 | 1 核 | 512MB | 200MB |
| 生产（单用户） | 1 核 | 512MB | 1GB |
| 生产（多用户） | 2 核 | 1GB+ | 5GB+ |

---

## 快速开始

```bash
# 1. 进入项目目录
cd pyWork

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux

# 3. 安装依赖
pip install -e .

# 4. 启动服务
python -m app.main --http --port 8080
```

访问 http://localhost:8080 验证。第一个注册的用户自动成为管理员。

---

## 插件说明

### 内置插件

| 插件 | 说明 | 路由前缀 |
|------|------|---------|
| `blog` | 博客（Markdown 编辑器、标签、搜索） | `/blog` |
| `auth` | 认证（注册/登录、Session、GitHub OAuth、MCP Token） | `/auth`、`/login`、`/register` |
| `microblog` | 微博（发布、删除、首页混合展示） | `/microblog` |
| `about` | 留言板（访客留言、管理员审核） | `/about` |
| `notes` | 笔记（公开/私有、支持 Markdown） | `/notes` |
| `board` | 看板 + 定时任务 + 网站设置（管理员） | `/board` |

### 默认启用

```bash
--enabled blog,auth,microblog,about,notes,board
```

### 自定义插件

1. 在 `plugins/` 目录创建插件包
2. 继承 `Plugin` 基类，实现 `init()`、`routes()`、`mcp_tools()` 等方法
3. 参考 `plugins/blog/plugin.py` 作为示例
4. 启动时通过 `--enabled` 参数加载

---

## 启动方式

### 命令行参数

```bash
python -m app.main [选项]

选项:
  --db <path>          数据库路径 (默认: ./data/pywork.db)
  --plugins <dir>      插件目录 (默认: ./plugins)
  --enabled <list>     启用的插件，逗号分隔
  --http               启动 HTTP 服务器
  --mcp-stdio          启动 MCP stdio 服务
  --host <host>        监听地址 (默认: 0.0.0.0)
  --port <port>        监听端口 (默认: 8080)
```

### HTTP 模式

```bash
# 开发
python -m app.main --http --port 8080

# 自定义数据库和插件
python -m app.main --http --db /data/pywork.db --enabled blog,notes

# 后台运行
nohup python -m app.main --http --port 8080 > pywork.log 2>&1 &
```

### MCP stdio 模式

供 AI 助手（Claude Desktop、Cursor 等）通过 MCP 协议调用：

```bash
python -m app.main --mcp-stdio
```

---

## API 参考

### 系统接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页 |
| GET | `/health` | 健康检查 |
| GET | `/api` | API 状态 |

### 认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/login` | 登录页 |
| GET | `/register` | 注册页 |
| POST | `/auth/login` | 登录 |
| POST | `/auth/register` | 注册（需验证码） |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前用户信息 |
| GET | `/auth/captcha` | 获取验证码 |
| GET | `/auth/github` | GitHub OAuth |
| GET | `/auth/github/callback` | GitHub 回调 |
| GET | `/auth/mcp-tokens` | MCP Token 列表 |
| POST | `/auth/mcp-tokens` | 创建 MCP Token |
| DELETE | `/auth/mcp-tokens/{token_id}` | 删除 MCP Token |
| GET | `/api/mcp-config` | MCP 配置 |

### 博客接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/blog` | 博客列表页 |
| GET | `/blog/new` | 新建博客页 |
| GET | `/blog/view/{post_id}` | 博客详情页 |
| GET | `/blog/posts` | API: 文章列表 |
| POST | `/blog/posts` | API: 创建文章 |
| GET | `/blog/posts/{post_id}` | API: 获取文章 |
| PUT | `/blog/posts/{post_id}` | API: 更新文章 |
| DELETE | `/blog/posts/{post_id}` | API: 删除文章 |
| GET | `/blog/search` | API: 搜索文章 |

### 微博接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/microblog` | 微博首页 |
| POST | `/microblog` | 发布微博 |
| GET | `/api/microblog` | API: 微博列表 |
| DELETE | `/api/microblog/{post_id}` | API: 删除微博 |

### 笔记接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/notes` | 笔记列表页 |
| GET | `/notes/new` | 新建笔记页 |
| GET | `/notes/{note_id}` | 笔记详情页 |
| POST | `/notes` | API: 创建笔记 |
| PUT | `/notes/{note_id}` | API: 更新笔记 |
| DELETE | `/notes/{note_id}` | API: 删除笔记 |
| GET | `/api/notes` | API: 我的笔记列表 |
| GET | `/api/notes/{note_id}` | API: 笔记详情 |

### 留言板接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/about` | 留言板页 |
| POST | `/about/comments` | 提交留言 |
| POST | `/about/comments/{id}/approve` | 审核留言（管理员） |
| DELETE | `/about/comments/{id}` | 删除留言 |
| GET | `/about/admin/comments` | 留言管理页（管理员） |

### 看板接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/board` | 看板页 |
| POST | `/board/tasks` | 创建任务 |
| PUT | `/board/tasks/{task_id}` | 更新任务 |
| DELETE | `/board/tasks/{task_id}` | 删除任务 |
| GET | `/board/cron` | 定时任务管理页 |
| GET | `/board/cron/jobs` | 定时任务列表 |
| POST | `/board/cron/jobs` | 创建定时任务 |
| PUT | `/board/cron/jobs/{job_id}` | 更新定时任务 |
| DELETE | `/board/cron/jobs/{job_id}` | 删除定时任务 |
| POST | `/board/cron/jobs/{job_id}/run` | 手动执行定时任务 |
| GET | `/board/settings` | 网站设置页 |
| GET | `/board/settings/api` | 获取设置 |
| PUT | `/board/settings/api` | 更新设置 |

---

## MCP 集成

### 配置 Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

### 配置 Cursor

编辑 `.cursor/mcp.json`:

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

### 认证方式

MCP 工具调用需提供 `api_token` 参数（在个人中心创建 MCP Token）。

### 可用工具

| 工具名 | 说明 | 主要参数 |
|--------|------|---------|
| `blog.create_post` | 创建文章 | title, content, status?, tags? |
| `blog.search_posts` | 搜索文章 | status?, tags?, limit? |
| `blog.update_post` | 更新文章 | id, title?, content?, status? |
| `blog.delete_post` | 删除文章 | id |

---

## 生产部署

### systemd 服务（Linux）

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
ExecStart=/opt/pywork/.venv/bin/python -m app.main --http --port 8080 --db /data/pywork.db
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# 部署
sudo useradd -r -s /bin/false pywork
sudo mkdir -p /opt/pywork /data
sudo chown pywork:pywork /opt/pywork /data

sudo -u pywork git clone <repo-url> /opt/pywork
cd /opt/pywork
sudo -u pywork python3 -m venv .venv
sudo -u pywork .venv/bin/pip install -e .

sudo systemctl daemon-reload
sudo systemctl enable pywork
sudo systemctl start pywork
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

1. **HTTPS**：使用 Let's Encrypt 配置 SSL
2. **防火墙**：仅开放 80/443，内部转发到 8080
3. **备份**：定期备份 `data/pywork.db`（SQLite 在线热备份：`sqlite3 pywork.db ".backup backup.db"`）
4. **更新**：定期更新依赖 `pip install --upgrade -e .`

---

## 常见问题

### Q: 端口被占用？

```bash
lsof -i :8080
kill -9 <PID>
# 或换端口
python -m app.main --http --port 8081
```

### Q: 如何重置管理员密码？

```bash
python -c "
from app.storage.sqlite_engine import SQLiteEngine
import asyncio, hashlib, secrets

async def reset():
    engine = SQLiteEngine('./data/pywork.db')
    await engine.start()          # 注意：是 start() 不是 init()
    salt = secrets.token_hex(16)
    pw = hashlib.pbkdf2_hmac('sha256', b'new_password', bytes.fromhex(salt), 100000)
    await engine.execute('UPDATE users SET password_hash=? WHERE role=?', (f'{salt}:{pw.hex()}', 'admin'))
    print('done')

asyncio.run(reset())
"
```

### Q: 数据库在哪？

默认 `./data/pywork.db`，可通过 `--db` 指定。**表结构随服务启动自动初始化，无需手动建库。**

启动时会自动创建以下表：

| 表名 | 所属插件 | 说明 |
|------|---------|------|
| `users` | 核心 | 用户 |
| `contents` | 核心 | 所有内容（博客/微博/笔记/留言） |
| `objects` | 核心 | 文件对象 |
| `tasks` | 核心 | 任务 |
| `plugins` | 核心 | 插件注册 |
| `templates` | 核心 | 模板 |
| `board_tasks` | board | 看板任务 |
| `cron_jobs` | board | 定时任务定义 |
| `cron_stats` | board | 定时任务统计结果 |
| `active_authors` | board | 活跃作者统计 |
| `site_config` | board | 网站配置（logo_text 等） |
| `_raft_log` | 核心 | Raft 日志（Phase 2+ 预留）|
| `_meta` | 核心 | 键值存储 |

> 注意：`mcp_tokens` 存储在内存中（重启丢失），如需持久化请修改 AuthPlugin 改存数据库。

### Q: MCP 连接失败？

1. 检查 Python 路径是否指向虚拟环境：`.venv/bin/python`
2. 检查工作目录是否正确
3. 查看 AI 助手的 MCP 调试日志
