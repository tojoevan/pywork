# pyWork 代码审查报告

> 审查日期：2026-04-20 ~ 2026-04-22  
> 项目：pyWork (Python/FastAPI/SQLite 多用户工作台)  
> 状态：✅ 全部完成

---

## 执行摘要

pyWork 是一个面向分布式部署的多用户数字工作台，当前处于 Phase 1（单机 SQLite）。本次代码审查发现并修复了 23 个问题，新增 117 个测试用例，项目已具备生产部署条件。

---

## 修复统计

| 级别 | 总数 | 说明 |
|------|------|------|
| P0 | 3 | 紧急 Bug，影响核心功能 |
| P1 | 6 | 高优问题，安全隐患 |
| P2 | 5 | 中期改进，架构优化 |
| P3 | 9 | 低优改进，代码质量 |
| **合计** | **23** | **100% 完成** |

---

## P0 紧急修复

### P0-1. 闭包变量捕获 Bug
**位置：** `app/main.py` — `_register_route` 方法

**问题：** Python 闭包通过引用捕获外层变量，循环中所有 `post_handler` 共享同一个 `route` 引用，导致全部 POST/PUT 路由指向最后一次注册的 route。

**修复：**
```python
# 修复前
async def post_handler(request: Request):
    result = await route.handler(request, **dict(body))

# 修复后
async def post_handler(request: Request, _route=route):  # 默认参数值捕获
    result = await _route.handler(request, **dict(body))
```

### P0-2. visibility 字段缺失
**位置：** `app/storage/sqlite_engine.py`

**问题：** microblog/notes 插件使用 `visibility` 字段，但 schema 未定义，新部署直接报错。

**修复：** 添加 Migration 001，启动时自动检测并添加列：
```sql
ALTER TABLE contents ADD COLUMN visibility TEXT DEFAULT 'private';
```

### P0-3. 调用不存在的 Engine 方法
**位置：** `plugins/auth/plugin.py`

**问题：** `engine.update()` 和 `engine.list()` 方法不存在。

**修复：** 改用已存在的方法：
- `update()` → `get()` + 合并 + `put()`
- `list()` → `fetchall()` + SQL

---

## P1 高优修复

### P1-1. SQL 注入风险
**位置：** `app/storage/sqlite_engine.py`

**问题：** 表名直接拼入 SQL，缺少白名单校验。

**修复：**
```python
ALLOWED_TABLES = frozenset({
    'users', 'blog_posts', 'microblog_posts', 'notes', ...
})

def _validate_table(self, table: str):
    if table not in self.ALLOWED_TABLES:
        raise ValueError(f"Table not allowed: {table}")
```

### P1-2. MCP Token 纯内存存储
**位置：** `plugins/auth/plugin.py`

**问题：** `self.mcp_tokens: Dict` 纯内存存储，重启丢失。

**修复：** 新增 `mcp_tokens` SQLite 表，重写所有相关方法。

### P1-3. Raft 日志无限膨胀
**位置：** `app/storage/sqlite_engine.py`

**问题：** 每次 `put`/`delete` 追加日志，无清理机制。

**修复：** 添加 `compact()` 方法，达到阈值后自动清理 30 天前的只读日志。

### P1-4. `_init_*_table` 重复执行
**位置：** `plugins/board/plugin.py`

**问题：** 每个 API handler 开头调用 `CREATE TABLE IF NOT EXISTS`。

**修复：** 统一 `_ensure_tables()` 入口，用 flag 防重。

### P1-5. 密码哈希格式不一致
**位置：** `plugins/auth/plugin.py`

**问题：** `_hash_password` 输出 `salt:hash`，`change_password` 输出 `salt:$hash`。

**修复：** 统一为 `salt:hash` 格式。

### P1-6. 鉴权逻辑重复
**位置：** 所有插件

**问题：** 相同鉴权代码重复 15+ 次。

**修复：** Plugin 基类新增统一方法：
- `get_current_user()`
- `get_current_user_mcp()`
- `is_admin()`
- `require_admin()`
- `require_admin_or_redirect()`
- `require_login_or_redirect()`

---

## P2 中期改进

### P2-1. contents 表职责过载
**问题：** blog/microblog/note/guestbook 全塞一张表，字段语义混乱。

**修复：** Migration 002 拆分为 4 张表：`blog_posts`、`microblog_posts`、`notes`、`guestbook_entries`。

### P2-2. 分页缺失
**问题：** 所有列表查询只有 `LIMIT N`，无 offset。

**修复：** 各插件统一添加 `limit`/`offset` 参数。

### P2-3. FTS5 全文搜索被注释
**问题：** `contents_fts` 建表语句被注释，搜索功能不可用。

**修复：** Migration 004 启用 FTS5，添加自动同步触发器。

### P2-4. 方法重定义
**问题：** `notes/plugin.py` 中 `update_note` 定义两次。

**修复：** 已在之前 commit 中删除。

### P2-5. 类变量可变状态
**问题：** `_ip_rate_limit: Dict` 类变量，多实例共享。

**修复：** 已在之前 commit 中改为实例变量。

---

## P3 低优改进

| # | 问题 | 修复方案 |
|---|------|----------|
| 3-1 | 错误处理不一致 | Plugin 基类添加 `error_json()`/`error_html()` |
| 3-2 | 无日志框架 | 新增 `app/log.py`，三通道输出（控制台+文件+SQLite） |
| 3-3 | 无配置验证 | 新增 `app/config.py`，Pydantic 模型 + 三层优先级 |
| 3-4 | 测试覆盖不足 | 新增 117 个测试用例 |
| 3-5 | 依赖不一致 | 同步 `pyproject.toml` 与 `requirements.txt` |
| 3-6 | Markdown XSS | 添加 HTML 标签/属性白名单过滤 |
| 3-7 | Session 双写 | 删除内存 dict 写入，仅保留 SQLite |
| 3-8 | 重复路由注册 | 删除 `main.py` 中手动注册的 `/microblog` |
| 3-9 | 首页逻辑内联 | 新增 `HomeService`，并行聚合首页数据 |

---

## 测试覆盖

| 测试文件 | 用例数 | 覆盖范围 |
|----------|--------|----------|
| test_home_service.py | 19 | HomeService 首页数据聚合 |
| test_auth.py | 27 | 验证码、密码哈希、注册、登录、Session、MCP Token、GitHub OAuth |
| test_mcp.py | 33 | MCP 协议握手、tools/resources/prompts、错误处理 |
| test_plugins.py | 38 | Blog/Notes/Microblog CRUD、跨插件、边界情况 |
| **总计** | **117** | — |

---

## 关键文件变更

### 新增
```
app/log.py                    # 日志框架
app/config.py                 # 配置验证层
app/services/home_service.py  # 首页数据聚合
tests/test_*.py               # 117 个测试用例
```

### 修改
```
app/main.py                   # 闭包修复、HomeService 集成
app/storage/sqlite_engine.py  # 白名单、迁移、FTS5
app/plugin/interface.py       # 鉴权方法、错误处理
app/template/engine.py        # XSS 过滤
plugins/auth/plugin.py        # MCP Token 持久化
plugins/board/plugin.py       # 日志路由、cron_logs
```

---

## 下一步建议

1. **生产部署** — 参考 `doc/PROD-UPGRADE.md` 执行迁移
2. **监控告警** — 配置日志收集和错误告警
3. **性能优化** — 考虑添加缓存层（Redis）
4. **API 文档** — 补充 OpenAPI 文档
