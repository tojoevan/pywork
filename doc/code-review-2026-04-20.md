# pyWork 项目代码审查报告

> 审查日期：2026-04-20
> P0 修复日期：2026-04-20
> P1 修复日期：2026-04-20 ~ 2026-04-21
> 审查范围：pyWork v0.1 全部源码
> 技术栈：Python 3.11+ / FastAPI / SQLite / Jinja2 / MCP

## P0 修复记录（2026-04-20）

### ✅ P0-1. 闭包变量捕获 Bug — 已修复
- **文件：** `app/main.py` — `_register_route` 方法
- **修复：** `post_handler` 和 `get_handler` 闭包参数改为 `_route=route`（默认参数值捕获）
- **验证：** `grep '_route=route' app/main.py` 匹配 3 处

### ✅ P0-2. visibility 字段缺失 — 已修复
- **文件：** `app/storage/sqlite_engine.py`
- **修复：** SCHEMA 中 contents 表添加 `visibility TEXT DEFAULT 'private'`；新增 `_run_migrations()` 方法，启动时自动检测并 ALTER TABLE 添加缺失列
- **验证：** 新数据库直接建表包含字段；旧数据库启动时自动迁移

### ✅ P0-3. 不存在的 Engine 方法 — 已修复
- **文件：** `plugins/auth/plugin.py`
- **修复：**
  - `update_user()`: 改用 `engine.get()` + 合并 + `engine.put()`
  - `change_password()`: 改用 `engine.put()` + 统一密码格式为 `salt:hash`
  - `list_users()`: 改用 `engine.fetchall()` + SQL
- **附带修复：** 密码哈希格式统一为 `salt:hash`（原 `change_password` 用 `$` 分隔）

---

## P1 修复记录（2026-04-20 ~ 2026-04-21）

### ✅ P1-1. SQL 注入 — 表名白名单 — 已修复
- **文件：** `app/storage/sqlite_engine.py`
- **修复：** 新增 `ALLOWED_TABLES` 集合 + `_validate_table()` 方法，在 `get`/`put`/`delete`/`query` 四个入口加校验；`execute`/`fetchone`/`fetchall` 不限制（调用者已有完整 SQL 控制权）；`mcp_tokens` 表已加入白名单

### ✅ P1-2. MCP Token 持久化 — 已修复
- **文件：** `plugins/auth/plugin.py`
- **修复：** 删除内存 dict `self.mcp_tokens`，新增 `mcp_tokens` SQLite 表（token TEXT PK, user_id, name, created_at, last_used），重写 `create_mcp_token`/`revoke_mcp_token`/`list_mcp_tokens`/`get_user_by_mcp_token` 四个方法为 SQL 操作

### ✅ P1-3. Raft 日志清理 — 已修复
- **文件：** `app/storage/sqlite_engine.py`
- **修复：** 新增 `compact()` 方法，在 `put()` 中达到阈值后自动清理旧日志；启动时也会执行一次

### ✅ P1-4. `_init_*_table` 重复执行 — 已修复
- **文件：** `plugins/board/plugin.py`
- **修复：** 新增 `_ensure_tables()` 统一入口，设 `self._tables_initialized` flag 防重，删除 11 处方法内冗余调用

### ✅ P1-5. 密码哈希格式不一致 — 已修复（P0 修复时顺带完成）
- 统一为 `salt:hash` 格式，删除 `$` 前缀逻辑

### ✅ P1-6. 鉴权逻辑去重 — 已修复
- **文件：** `app/plugin/interface.py` + 所有插件
- **修复：**
  - Plugin 基类新增 6 个统一鉴权方法：`get_current_user`、`get_current_user_mcp`、`is_admin`、`require_admin`、`require_admin_or_redirect`、`require_login_or_redirect`
  - 所有插件添加 `self._ctx = ctx`，删除本地 `_auth()`/`_get_auth_plugin()`/`_get_current_user()`/`_get_current_user_mcp()`/`_is_admin()`/`_check_admin()`/`_check_admin_or_redirect()` 等重复方法
  - 调用方全部改为使用基类方法

---

## 执行摘要

pyWork 是一个面向分布式部署的多用户数字工作台，当前处于 Phase 1（单机 SQLite）。项目整体架构设计清晰，Raft-ready 的存储层抽象为未来演进预留了良好基础。但代码中存在若干影响稳定性和可维护性的问题，**其中 3 个 P0 级问题必须尽快修复**。

---

## P0 — 必须立即修复

### 🔴 0-1. 闭包变量捕获 Bug

**位置：** `app/main.py` — `_register_route` 方法内部

```python
def _register_route(self, route):
    if route.method in ("POST", "PUT"):
        async def post_handler(request: Request):  # ← 闭包引用，非值捕获
            body = await request.form()
            result = await route.handler(request, **dict(body))
```

Python 闭包通过**引用**捕获外层变量，不是值拷贝。当循环中多次调用 `_register_route` 时，所有 `post_handler` 闭包共享同一个 `route` 变量引用——导致全部 POST/PUT 路由指向最后一次注册的 route。

**影响：** 所有 POST/PUT API 路由行为异常或全部失效。

**修复方案：**

```python
def _register_route(self, route):
    if route.method in ("POST", "PUT"):
        async def post_handler(request: Request, _route=route):  # 默认参数值捕获
            body = await request.form()
            result = await _route.handler(request, **dict(body))
```

### 🔴 0-2. `visibility` 字段缺失（Migration 缺失）

**位置：** `plugins/microblog/plugin.py`、`plugins/notes/plugin.py`

两个插件在写入和查询时使用 `visibility` 字段：

```python
# microblog plugin
post["status"] = visibility  # line ~95

# notes plugin — 查询时
conditions.append("(author_id = ? OR visibility = 'public')")
```

但 `contents` 表 schema（`sqlite_engine.py`）没有定义此列。该字段可能通过运行时的 `ALTER TABLE` 动态加上了，但没有任何 migration 脚本记录。

**影响：** 新部署或干净数据库启动后，查询直接报错；代码与 schema 不同步。

**修复方案：** 编写正式 migration 脚本：

```sql
ALTER TABLE contents ADD COLUMN visibility TEXT DEFAULT 'private';
```

### 🔴 0-3. 调用不存在的 Engine 方法

**位置：** `plugins/auth/plugin.py`

```python
# change_password 方法
await self.engine.update("users", kwargs)  # Engine 接口无此方法

# list_users 方法
users = await self.engine.list("users", limit=limit, offset=offset)  # 无此方法
```

`Engine` 接口（`storage/interface.py`）仅定义了 `get`、`put`、`delete`、`query`、`fetchall`、`fetchone`、`execute` 七个方法。`update` 和 `list` 不存在。

**影响：** 调用 `change_password` 或 MCP `auth_list_mcp_tokens` 中的 `list_users` 时直接抛出 `AttributeError`。

**修复方案：** 改用已存在的方法：

```python
# list_users 改为
rows = await self.engine.fetchall(
    "SELECT * FROM users LIMIT ? OFFSET ?", (limit, offset)
)

# change_password 改为
await self.engine.put("users", user_id, {"password_hash": new_hash})
```

---

## P1 — 高优先级

### 🟠 1-1. SQL 注入风险

**位置：** `storage/sqlite_engine.py` — `get`、`put`、`delete`、`query`

```python
async def get(self, table: str, record_id: int):
    return await self._db.execute(f"SELECT * FROM {table} WHERE id = ?", ...)
```

虽然目前 `table` 参数都是内部硬编码字符串，但违背纵深防御原则。`contents`、`users` 等关键表名直接拼入 SQL，缺少白名单校验。

**修复方案：** 添加表名白名单：

```python
ALLOWED_TABLES = {'users', 'contents', 'sessions', 'site_config',
                  'cron_jobs', 'cron_stats', 'board_tasks', 'active_authors'}

def _validate_table(self, table: str):
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table not allowed: {table}")
```

### 🟠 1-2. MCP Token 纯内存存储

**位置：** `plugins/auth/plugin.py`

```python
self.mcp_tokens: Dict[str, Dict] = {}  # 内存 dict
```

重启即丢失，且无过期清理。作为持久化认证凭证设计，这是架构缺陷。

**修复方案：** 迁移到 SQLite 表 `mcp_tokens(token TEXT PRIMARY KEY, ...)`。

### 🟠 1-3. Raft 日志无限膨胀

**位置：** `storage/sqlite_engine.py` — `_raft_log` 表

每次 `put`/`delete` 都向 `_raft_log` 追加一条记录，没有任何清理机制（无 snapshot、无 compaction、无定期删除）。

**修复方案（Phase 1 过渡期）：**

```python
# 定期清理 30 天前的只读日志
await self.engine.execute(
    "DELETE FROM _raft_log WHERE index < ? AND index NOT IN (SELECT max_index FROM node_state)",
    (current_index - 10000,)
)
)
```

### 🟠 1-4. `_init_*_table` 重复执行

**位置：** `plugins/board/plugin.py`

`_init_board_table`、`_init_cron_tables`、`_init_active_authors_table` 在每个 API handler 开头调用，频繁执行 `CREATE TABLE IF NOT EXISTS`。

**修复方案：** 在 `init()` 或应用 startup 时统一执行一次；或用 Python 模块级 flag 保证只跑一次。

### 🟠 1-5. 密码哈希格式不一致

**位置：** `plugins/auth/plugin.py`

- `_hash_password`：输出格式 `salt:hash`
- `change_password`：输出格式 `salt:$hash`（含 `$` 前缀）
- `_split_password_hash`：兼容 `:` 和 `$` 分隔
- `_verify_password`：只处理 `$` 分隔

新旧格式混用，未来扩展字段时必然出问题。

**修复方案：** 统一用 `salt:hash` 格式，删除 `$` 前缀逻辑。

### 🟠 1-6. 鉴权逻辑重复

**位置：** 几乎所有插件

```python
# 出现了 15+ 次的相同模式
token = request.cookies.get("auth_token", "")
if not token:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
auth = self._get_auth_plugin()
if auth:
    user = await auth.get_user_by_token(token)
```

**修复方案：** 实现 FastAPI 依赖注入或装饰器：

```python
# 实现 auth.py 中
async def get_current_user(request: Request, auth: AuthPlugin):
    token = request.cookies.get("auth_token", "")
    if not token:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return await auth.get_user_by_token(token)

# FastAPI 路由使用
from starlette.testclient import TestClient
```

---

## P2 — 中期改进

### 🟡 2-1. `contents` 表职责过载

**现状：** blog、microblog、note、guestbook 全塞进一张表，字段语义混乱：

| plugin_type | title 含义 | body 含义 |
|-------------|-----------|----------|
| blog | 博客标题 | 博客正文 |
| microblog | 空 | 微博正文 |
| note | 笔记标题 | 笔记正文 |
| guestbook | 留言者昵称 | 留言内容 |

**建议：** 按 Phase 2 演进规划拆分，或至少引入插件注册机制让各插件声明自己需要的扩展字段。

### 🟡 2-2. 分页缺失

所有列表查询都是 `LIMIT N`，无 offset 分页。

**建议：** 统一分页参数 `{limit, offset}` 或 `{page, page_size}`，封装公共查询方法。

### 🟡 2-3. FTS5 全文搜索被注释

**位置：** `sqlite_engine.py` 建表语句

`CREATE VIRTUAL TABLE IF NOT EXISTS contents_fts USING fts5(...)` 被注释掉，但 `blog/search_posts` 引用了它：

```python
conditions.append("id IN (SELECT rowid FROM contents_fts WHERE contents_fts MATCH ?)")
```

搜索功能实际不可用。

**修复：** 取消注释并补充迁移脚本：

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS contents_fts USING fts5(
    title, body, tags, content='contents', content_rowid='id'
);
```

### 🟡 2-4. `notes/plugin.py` 方法重定义

`update_note` 方法定义了两次，第二个覆盖第一个。第一个版本缺少 `mcp_token` 参数，是死代码。

**修复：** 删除重复定义，保留含 `mcp_token` 的版本。

### 🟡 2-5. 类变量可变状态

**位置：** `plugins/microblog/plugin.py`

```python
class MicroblogPlugin(Plugin):
    _ip_rate_limit: Dict[str, float] = {}  # 类变量，所有实例共享
```

多实例场景下共享数据。应在 `__init__` 中定义为实例变量。

---

## P3 — 改进建议

| # | 问题 | 说明 |
|---|------|------|
| 3-1 | 错误处理不一致 | 返回格式混乱：`{"error"}` vs `JSONResponse` vs `HTMLResponse` |
| 3-2 | 无日志框架 | 全项目只有 `print()`，无结构化日志 |
| 3-3 | 无配置验证层 | 所有配置硬编码或环境变量，缺乏 Schema 验证 |
| 3-4 | 测试覆盖不足 | 仅 `test_storage.py`、`test_blog.py`，auth/MCP/插件无测试 |
| 3-5 | 依赖不一致 | `requirements.txt` 与 `pyproject.toml` 不同步（缺 pillow/multipart/dotenv）|
| 3-6 | Markdown XSS | `markdown_filter` 生成的 HTML 未做 XSS 过滤 |
| 3-7 | Session 双写 | 内存 dict + SQLite 同时写，中间崩溃不一致 |
| 3-8 | 重复路由注册 | `microblog_index` 在 main.py 手动注册后又通过 plugin routes 注册 |
| 3-9 | 首页逻辑内联 | `/` 路由内联 6+ 个查询，耦合过重 |

---

## 建议修复优先级

```
立即修复（P0）：
  [FIX] main.py — _register_route 闭包 Bug
  [FIX] schema — 添加 visibility 列 migration
  [FIX] auth.py — 删除/替换不存在的 engine 方法

本周内（P1）：
  [FIX] sqlite_engine.py — 表名白名单
  [FIX] auth.py — MCP Token 持久化
  [FIX] board.py — _init_* 移到 startup
  [FIX] auth.py — 密码格式统一
  [NEW] 中间件/装饰器 — 统一鉴权

下个月（P2）：
  [REFACTOR] contents 表拆分规划
  [NEW] 统一分页方案
  [FIX] FTS5 建表取消注释
  [FIX] notes plugin 删除死代码
  [FIX] microblog 类变量改为实例变量
  [NEW] 测试覆盖率提升（pytest）
  [SYNC] requirements.txt / pyproject.toml
```

---

## 附录：关键文件索引

| 文件 | 角色 |
|------|------|
| `app/main.py` | 应用入口，WorkbenchApp，路由注册 |
| `app/storage/interface.py` | Engine 抽象接口（Raft-ready） |
| `app/storage/sqlite_engine.py` | SQLite 实现，建表语句 |
| `app/plugin/interface.py` | Plugin 系统接口 |
| `app/mcp/server.py` | MCP Server 实现 |
| `app/template/engine.py` | Jinja2 模板引擎 |
| `plugins/auth/plugin.py` | 认证插件（含 GitHub OAuth）|
| `plugins/blog/plugin.py` | 博客插件 |
| `plugins/microblog/plugin.py` | 微博插件 |
| `plugins/notes/plugin.py` | 笔记插件 |
| `plugins/board/plugin.py` | 看板+定时任务+设置 |
| `plugins/about/plugin.py` | 关于页面+留言板 |

---

## 修复进度总表

> 更新日期：2026-04-21

| 编号 | 级别 | 问题 | 状态 | 修复日期 | 修改文件 |
|------|------|------|------|----------|----------|
| P0-1 | 🔴 P0 | 闭包变量捕获 Bug | ✅ 已修复 | 2026-04-20 | `app/main.py` |
| P0-2 | 🔴 P0 | visibility 字段缺失 | ✅ 已修复 | 2026-04-20 | `app/storage/sqlite_engine.py` |
| P0-3 | 🔴 P0 | 调用不存在的 Engine 方法 | ✅ 已修复 | 2026-04-20 | `plugins/auth/plugin.py` |
| P1-1 | 🟠 P1 | SQL 注入 — 表名白名单 | ✅ 已修复 | 2026-04-20 | `app/storage/sqlite_engine.py` |
| P1-2 | 🟠 P1 | MCP Token 纯内存存储 | ✅ 已修复 | 2026-04-20 | `plugins/auth/plugin.py` |
| P1-3 | 🟠 P1 | Raft 日志无限膨胀 | ✅ 已修复 | 2026-04-20 | `app/storage/sqlite_engine.py` |
| P1-4 | 🟠 P1 | `_init_*_table` 重复执行 | ✅ 已修复 | 2026-04-20 | `plugins/board/plugin.py` |
| P1-5 | 🟠 P1 | 密码哈希格式不一致 | ✅ 已修复 | 2026-04-20 | `plugins/auth/plugin.py` |
| P1-6 | 🟠 P1 | 鉴权逻辑重复 | ✅ 已修复 | 2026-04-21 | `app/plugin/interface.py` + 所有插件 |
| P2-1 | 🟡 P2 | `contents` 表职责过载 | ✅ 已修复 | 2026-04-21 | `app/storage/sqlite_engine.py` (Migration 002 拆表) |
| P2-2 | 🟡 P2 | 分页缺失 | ✅ 已修复 | 2026-04-21 | 各插件 list 方法 |
| P2-3 | 🟡 P2 | FTS5 全文搜索被注释 | ✅ 已修复 | 2026-04-21 | `app/storage/sqlite_engine.py` (Migration 004) |
| P2-4 | 🟡 P2 | `notes/plugin.py` 方法重定义 | ✅ 已有修复 | 2026-04-21 | 确认 commit 993758a 已删除重复定义 |
| P2-5 | 🟡 P2 | 类变量可变状态 | ✅ 已有修复 | 2026-04-21 | 确认 `_ip_rate_limit` 已改为实例变量 |
| P3-1 | 🟢 P3 | 错误处理不一致 | ✅ 已修复 | 2026-04-21 | `interface.py` + `main.py` + 4个插件 |
| P3-2 | 🟢 P3 | 无日志框架 | ✅ 已修复 | 2026-04-22 | `app/log.py` + 全项目 print() 已迁移 |
| P3-3 | 🟢 P3 | 无配置验证层 | ✅ 已修复 | 2026-04-22 | `app/config.py` (pydantic AppConfig + SiteConfigManager) |
| P3-4 | 🟢 P3 | 测试覆盖不足 | ✅ 已修复 | 2026-04-22 | tests/test_auth.py (27) + test_mcp.py (33) + test_plugins.py (38) + test_home_service.py (19) = 117 用例 |
| P3-5 | 🟢 P3 | 依赖不一致 | ✅ 已修复 | 2026-04-21 | `pyproject.toml` + `requirements.txt` |
| P3-6 | 🟢 P3 | Markdown XSS | ✅ 已修复 | 2026-04-21 | `app/template/engine.py` (白名单过滤) |
| P3-7 | 🟢 P3 | Session 双写 | ✅ 已修复 | 2026-04-21 | `plugins/auth/plugin.py` (删除内存写) |
| P3-8 | 🟢 P3 | 重复路由注册 | ✅ 已修复 | 2026-04-21 | `app/main.py` (删除手动注册) |
| P3-9 | 🟢 P3 | 首页逻辑内联 | ✅ 已修复 | 2026-04-22 | `app/services/home_service.py` + `app/main.py` |

### 统计

| 级别 | 总数 | 已修复 | 未修复 |
|------|------|--------|--------|
| P0 | 3 | 3 | 0 |
| P1 | 6 | 6 | 0 |
| P2 | 5 | 5 | 0 |
| P3 | 9 | 9 | 0 |
| **合计** | **23** | **23** | **0** |

### 测试覆盖

| 测试文件 | 用例数 | 覆盖范围 |
|----------|--------|----------|
| tests/test_home_service.py | 19 | HomeService 首页数据聚合 |
| tests/test_auth.py | 27 | 验证码、密码哈希、注册、登录、Session、MCP Token、GitHub OAuth |
| tests/test_mcp.py | 33 | MCP 协议握手、tools/resources/prompts、错误处理 |
| tests/test_plugins.py | 38 | Blog/Notes/Microblog CRUD、跨插件、边界情况 |
| **总计** | **117** | — |

**🎉 所有 23 项代码审查问题已全部修复！测试覆盖 117 用例通过！**
