# pyWork 系统架构设计文档

> 版本：v0.1  
> 更新日期：2026-04-22  
> 状态：代码审查完成，生产就绪

---

## 1. 项目概述

### 1.1 定位
pyWork 是一个面向分布式部署的多用户数字工作台，支持博客、微博、笔记、看板等功能模块，提供 MCP (Model Context Protocol) 接口供 AI 助手调用。

### 1.2 技术栈
| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI (Starlette) |
| 数据库 | SQLite + aiosqlite |
| 模板引擎 | Jinja2 |
| Markdown | python-markdown + markdown-extra |
| 配置验证 | Pydantic v2 |
| 异步运行时 | asyncio + uvicorn |
| AI 接口 | MCP (Model Context Protocol) |

### 1.3 演进路线
```
Phase 1 (当前): 单机 SQLite
Phase 2: 主从复制
Phase 3: Raft 集群
Phase 4: 数据分片
```

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         用户请求                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI (app/main.py)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ HTTP Routes │  │ MCP Server  │  │ Template Engine     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Plugin System                             │
│  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌───────┐  │
│  │  blog  │ │  auth  │ │ microblog│ │ notes  │ │ board │  │
│  └────────┘ └────────┘ └──────────┘ └────────┘ └───────┘  │
│  ┌────────┐                                                 │
│  │  about │                                                 │
│  └────────┘                                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Engine Interface (Raft-ready)             │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              SQLiteEngine (Phase 1)                    │  │
│  │  - 表名白名单校验                                       │  │
│  │  - Raft 日志压缩                                       │  │
│  │  - 自动迁移机制                                         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    SQLite Database                           │
│  blog_posts | microblog_posts | notes | users | sessions    │
│  site_config | cron_jobs | cron_logs | app_logs | ...       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 请求处理流程

```
HTTP Request
    │
    ▼
┌──────────────────┐
│ FastAPI Router   │  路由匹配
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ Plugin Handler   │  插件处理（鉴权、业务逻辑）
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ Engine Interface │  存储抽象层
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ SQLiteEngine     │  表名校验 → SQL 执行 → Raft 日志
└──────────────────┘
    │
    ▼
┌──────────────────┐
│ Template Engine  │  渲染响应（HTML/JSON）
└──────────────────┘
    │
    ▼
HTTP Response
```

---

## 3. 核心模块设计

### 3.1 存储层 (Storage Layer)

#### 3.1.1 Engine 接口
```python
class Engine(ABC):
    """存储引擎抽象接口（Raft-ready）"""
    
    async def get(self, table: str, record_id: int) -> Optional[Dict]: ...
    async def put(self, table: str, record_id: int, data: Dict) -> int: ...
    async def delete(self, table: str, record_id: int) -> bool: ...
    async def query(self, table: str, conditions: Dict) -> List[Dict]: ...
    async def fetchall(self, sql: str, params: tuple) -> List[Dict]: ...
    async def fetchone(self, sql: str, params: tuple) -> Optional[Dict]: ...
    async def execute(self, sql: str, params: tuple) -> None: ...
```

#### 3.1.2 SQLiteEngine 实现
**关键特性：**

1. **表名白名单** — 防止 SQL 注入
   ```python
   ALLOWED_TABLES = frozenset({
       'users', 'blog_posts', 'microblog_posts', 'notes', 
       'guestbook_entries', 'sessions', 'cron_jobs', 'cron_logs',
       'site_config', 'mcp_tokens', 'app_logs', ...
   })
   ```

2. **Raft 日志** — 预留分布式演进
   ```python
   # 每次写操作追加日志
   await self.execute(
       "INSERT INTO _raft_log (term, index, command, timestamp) VALUES (?, ?, ?, ?)",
       (term, index, json.dumps(command), time.time())
   )
   ```

3. **自动迁移** — 启动时检测并执行
   ```python
   async def _run_migrations(self):
       # Migration 001: visibility 字段
       # Migration 002: contents 表拆分
       # Migration 003: mcp_tokens 表
       # Migration 004: FTS5 全文搜索
   ```

#### 3.1.3 数据库 Schema
```
核心业务表：
├── users (用户)
├── blog_posts (博客)
├── microblog_posts (微博)
├── notes (笔记)
├── guestbook_entries (留言板)
└── objects (文件)

系统表：
├── sessions (会话)
├── site_config (站点配置)
├── mcp_tokens (MCP 认证令牌)
├── cron_jobs (定时任务)
├── cron_logs (任务执行日志)
├── app_logs (应用日志)
└── active_authors (活跃作者缓存)

内部表：
├── _meta (元数据/迁移状态)
└── _raft_log (Raft 日志)
```

### 3.2 插件系统 (Plugin System)

#### 3.2.1 插件接口
```python
class Plugin(ABC):
    """插件基类"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    async def init(self, ctx: PluginContext): ...
    
    def routes(self) -> List[Route]: ...      # HTTP 路由
    def mcp_tools(self) -> List[MCPTool]: ...  # MCP 工具
    def mcp_resources(self) -> List[MCPResource]: ...  # MCP 资源
    def mcp_prompts(self) -> List[MCPPrompt]: ...  # MCP 提示模板
```

#### 3.2.2 插件上下文
```python
class PluginContext:
    """插件依赖注入容器"""
    engine: Engine                    # 存储引擎
    config: ConfigWrapper             # 配置（支持 .get() 和属性访问）
    template_engine: TemplateEngine   # 模板引擎
    
    def get_plugin(self, name: str):  # 获取其他插件
```

#### 3.2.3 统一鉴权方法
```python
class Plugin:
    # 基类提供的鉴权方法（所有插件共享）
    async def get_current_user(self, request) -> Optional[Dict]: ...
    async def get_current_user_mcp(self, mcp_token) -> Optional[Dict]: ...
    async def is_admin(self, request) -> bool: ...
    async def require_admin(self, request) -> Dict: ...
    async def require_admin_or_redirect(self, request) -> Dict: ...
    async def require_login_or_redirect(self, request) -> Dict: ...
    
    # 统一错误响应
    def error_json(self, message: str, code: int = 400) -> JSONResponse: ...
    def error_html(self, message: str, template: str = "error.html") -> HTMLResponse: ...
```

#### 3.2.4 插件列表
| 插件 | 功能 | MCP 工具 |
|------|------|----------|
| auth | 用户认证、GitHub OAuth、MCP Token | auth_create_mcp_token, auth_list_mcp_tokens, auth_revoke_mcp_token |
| blog | 博客文章 CRUD、FTS5 搜索 | blog_create_post, blog_update_post, blog_delete_post, blog_list_posts, blog_search_posts |
| microblog | 微博发布、IP 限流 | microblog_create_post, microblog_delete_post, microblog_list_posts |
| notes | 笔记管理 | notes_create_note, notes_update_note, notes_delete_note, notes_list_notes |
| board | 看板、定时任务、系统设置、日志浏览 | board_create_task, board_list_tasks, cron 相关 |
| about | 关于页面、留言板 | about_create_guestbook_entry, about_list_guestbook |

### 3.3 配置管理 (Config Management)

#### 3.3.1 三层配置优先级
```
环境变量 (PYWORK_*)  >  site_config 表  >  Pydantic 默认值
```

#### 3.3.2 AppConfig 模型
```python
class AppConfig(BaseModel):
    # 基础信息
    title: str = "pyWork"
    description: str = "多用户数字工作台"
    
    # 运行时
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    
    # 数据库
    db_path: str = "./data/pywork.db"
    
    # GitHub OAuth
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    
    # 上传
    upload_dir: str = "./data/uploads"
    max_upload_size: int = 10 * 1024 * 1024
    
    @field_validator("port")
    def validate_port(cls, v): ...
```

#### 3.3.3 自动迁移机制
启动时自动将新配置字段写入 `site_config` 表，确保升级平滑：
```python
async def build_config(engine) -> AppConfig:
    # 1. 从 site_config 表读取
    # 2. 环境变量覆盖
    # 3. Pydantic 验证 + 填默认值
    # 4. 新字段写回数据库
```

### 3.4 日志系统 (Logging)

#### 3.4.1 三通道输出
```python
setup_logging(data_dir, log_level, engine)
    │
    ├── ConsoleHandler (彩色输出)
    │
    ├── RotatingFileHandler (data/logs/pywork.log, 10MB × 5)
    │
    └── SQLiteHandler (app_logs 表)
```

#### 3.4.2 使用方式
```python
from app.log import get_logger

log = get_logger(__name__, "auth")  # 模块标签用于分类

log.info("用户登录", extra={"module": "auth"})
log.error("数据库错误", exc_info=True)
```

#### 3.4.3 日志浏览
Board 插件提供 `/board/logs` 页面：
- 按级别、模块、关键词过滤
- 分页浏览
- 30 天清理接口

### 3.5 模板引擎 (Template Engine)

#### 3.5.1 自定义过滤器
| 过滤器 | 功能 |
|--------|------|
| `datetime` | 时间戳 → ISO 格式 |
| `datefmt` | 时间戳 → 友好格式（刚刚、N 分钟前、N 天前） |
| `excerpt` | 提取摘要（移除 Markdown 标记） |
| `markdown` | Markdown → HTML（带 XSS 过滤） |

#### 3.5.2 XSS 防护
```python
def _sanitize_html_input(text: str) -> str:
    """白名单过滤 HTML 标签和属性"""
    safe_tags = {'br', 'p', 'pre', 'code', 'a', 'img', ...}
    safe_attrs = {'a': {'href', 'title'}, 'img': {'src', 'alt'}, ...}
    
    # 阻止 javascript: 协议
    if 'javascript:' in href.lower():
        href = '#'
```

### 3.6 MCP Server

#### 3.6.1 协议握手
```json
{
  "method": "initialize",
  "params": {...}
}
→
{
  "protocolVersion": "2024-11-05",
  "capabilities": {
    "tools": {},
    "resources": {},
    "prompts": {}
  },
  "serverInfo": {"name": "pyWork", "version": "0.1.0"}
}
```

#### 3.6.2 工具调用流程
```
AI 助手
    │
    ▼  tools/call (name="blog.create_post", arguments={...}, meta={token: "xxx"})
┌──────────────────┐
│  MCP Server      │  解析 plugin.tool
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Auth Plugin     │  验证 mcp_token → 获取 user_id
└──────────────────┘
    │
    ▼
┌──────────────────┐
│  Blog Plugin     │  执行 mcp_call("create_post", args, token)
└──────────────────┘
    │
    ▼
返回结果 {"id": 123, "title": "...", ...}
```

### 3.7 首页服务 (HomeService)

#### 3.7.1 设计目标
将首页 `/` 路由中内联的 6+ 个查询拆分到独立服务，实现：
- 单一职责
- 并行查询
- 易于测试

#### 3.7.2 数据聚合
```python
class HomeService:
    async def get_home_data(self, feed_limit=20) -> Dict:
        """并行获取首页全部数据"""
        feed_task = asyncio.create_task(self.get_feed(feed_limit))
        stats_task = asyncio.create_task(self.get_stats())
        authors_task = asyncio.create_task(self.get_active_authors())
        
        results = await asyncio.gather(
            feed_task, stats_task, authors_task,
            return_exceptions=True
        )
        ...
```

---

## 4. 安全设计

### 4.1 认证机制
| 场景 | 方式 |
|------|------|
| Web 页面 | Cookie (`auth_token`) + Session 表 |
| API 调用 | Header (`Authorization: Bearer <token>`) |
| MCP 调用 | `meta.token` (MCP Token) |

### 4.2 密码安全
```python
# 格式：salt:hash
def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hash.hex()}"

def _verify_password(password: str, stored: str) -> bool:
    salt, hash = stored.split(':')
    computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hmac.compare_digest(computed.hex(), hash)
```

### 4.3 SQL 注入防护
- 表名白名单校验 (`ALLOWED_TABLES`)
- 参数化查询（所有 SQL 使用 `?` 占位符）

### 4.4 XSS 防护
- Markdown 渲染前对用户输入做 HTML 白名单过滤
- 阻止 `javascript:` 协议

### 4.5 CSRF 防护
- 状态修改操作要求用户已登录
- MCP Token 独立于 Session

---

## 5. 性能优化

### 5.1 数据库
- **索引**：所有表的主键、`author_id`、`created_at` 字段
- **FTS5**：`blog_posts_fts` 全文搜索虚拟表
- **连接池**：aiosqlite 异步连接

### 5.2 缓存
- **SiteConfig**：30 秒内存缓存
- **Template**：Jinja2 模板编译缓存
- **Active Authors**：定时更新到 `active_authors` 表

### 5.3 并发
- **异步 I/O**：全链路 asyncio
- **并行查询**：首页数据 `asyncio.gather`

---

## 6. 测试覆盖

### 6.1 测试文件
| 文件 | 用例数 | 覆盖范围 |
|------|--------|----------|
| test_auth.py | 27 | 验证码、密码哈希、注册、登录、Session、MCP Token、GitHub OAuth |
| test_mcp.py | 33 | MCP 协议握手、tools/resources/prompts、错误处理 |
| test_plugins.py | 38 | Blog/Notes/Microblog CRUD、跨插件、边界情况 |
| test_home_service.py | 19 | HomeService 首页数据聚合 |
| **总计** | **117** | — |

### 6.2 运行测试
```bash
pytest tests/ -v
```

---

## 7. 部署

### 7.1 目录结构
```
pywork/
├── app/                 # 核心应用
│   ├── main.py          # 入口
│   ├── config.py        # 配置管理
│   ├── log.py           # 日志系统
│   ├── storage/         # 存储层
│   ├── plugin/          # 插件系统
│   ├── template/        # 模板引擎
│   ├── mcp/             # MCP Server
│   └── services/        # 业务服务
├── plugins/             # 插件实现
│   ├── auth/
│   ├── blog/
│   ├── microblog/
│   ├── notes/
│   ├── board/
│   └── about/
├── templates/           # 全局模板
├── static/              # 静态文件
├── data/                # 数据目录
│   ├── pywork.db        # SQLite 数据库
│   ├── logs/            # 日志文件
│   └── uploads/         # 上传文件
├── tests/               # 测试用例
├── doc/                 # 文档
├── pyproject.toml       # 项目配置
└── requirements.txt     # 依赖列表
```

### 7.2 生产部署
参考 `doc/PROD-UPGRADE.md`：
- systemd 服务配置
- nginx 反向代理
- 数据库迁移步骤

---

## 8. 代码审查总结

### 8.1 修复统计
| 级别 | 总数 | 状态 |
|------|------|------|
| P0 (紧急) | 3 | ✅ 全部修复 |
| P1 (高优) | 6 | ✅ 全部修复 |
| P2 (中期) | 5 | ✅ 全部修复 |
| P3 (改进) | 9 | ✅ 全部修复 |
| **总计** | **23** | **✅** |

### 8.2 关键修复
| 问题 | 修复方案 |
|------|----------|
| 闭包变量捕获 Bug | 默认参数值捕获 `_route=route` |
| visibility 字段缺失 | Migration 001 自动添加 |
| SQL 注入风险 | 表名白名单 `ALLOWED_TABLES` |
| MCP Token 内存存储 | 迁移到 `mcp_tokens` 表 |
| 鉴权逻辑重复 | Plugin 基类统一方法 |
| contents 表职责过载 | Migration 002 拆分为 4 张表 |
| FTS5 被注释 | Migration 004 启用 + 自动同步触发器 |
| 无日志框架 | `app/log.py` 三通道输出 |
| 无配置验证 | `app/config.py` Pydantic 模型 |
| 首页逻辑内联 | `HomeService` 并行聚合 |

---

## 9. 扩展指南

### 9.1 新增插件
1. 创建 `plugins/<name>/plugin.py`
2. 继承 `Plugin` 基类
3. 实现 `name`、`init()`、`routes()` 等方法
4. 在 `enabled_plugins` 中注册

### 9.2 新增 MCP 工具
```python
def mcp_tools(self):
    return [
        MCPTool(
            name="my_tool",
            description="工具描述",
            input_schema={
                "type": "object",
                "properties": {"param": {"type": "string"}},
                "required": ["param"]
            }
        )
    ]

async def mcp_call(self, tool_name: str, args: dict, mcp_token: str):
    user = await self.get_current_user_mcp(mcp_token)
    if tool_name == "my_tool":
        return {"result": ...}
```

### 9.3 数据库迁移
在 `sqlite_engine.py` 的 `_run_migrations()` 中添加：
```python
if not await self._check_migration("005"):
    await self._migrate_005()
    await self._mark_migration("005")
```

---

## 10. 附录

### 10.1 环境变量
| 变量 | 说明 |
|------|------|
| PYWORK_TITLE | 站点标题 |
| PYWORK_DEBUG | 调试模式 (true/false) |
| PYWORK_PORT | 监听端口 |
| PYWORK_DB_PATH | 数据库路径 |
| GITHUB_CLIENT_ID | GitHub OAuth Client ID |
| GITHUB_CLIENT_SECRET | GitHub OAuth Secret |

### 10.2 API 路由
| 路由 | 方法 | 插件 | 说明 |
|------|------|------|------|
| / | GET | main | 首页 |
| /auth/login | GET/POST | auth | 登录 |
| /auth/register | GET/POST | auth | 注册 |
| /blog | GET | blog | 博客列表 |
| /blog/new | GET/POST | blog | 新建博客 |
| /microblog | GET | microblog | 微博列表 |
| /notes | GET | notes | 笔记列表 |
| /board | GET | board | 看板 |
| /board/cron | GET | board | 定时任务 |
| /board/logs | GET | board | 日志浏览 |
| /mcp | POST | mcp | MCP 接口 |

### 10.3 相关文档
- `doc/code-review-2026-04-20.md` — 详细审查报告
- `doc/code-review-complete-summary.md` — 完成总结
- `doc/PROD-UPGRADE.md` — 生产升级指南
