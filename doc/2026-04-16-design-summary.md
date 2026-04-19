# 分布式系统完整设计方案 (Python + MCP)

> 整合时间: 2026-04-16
> 目标: 多用户数字工作台，支持博客、微博、笔记、RSS、待办、运维看板等功能，全对等节点，任意接入/退出，MCP协议对接AI

---

## 1. 系统定位

一个支持多用户的个人/小型团队数字工作台，每个节点都是**完全体**，可任意接入/退出，自动负载均衡，无中心依赖。通过**MCP协议**对外暴露能力，任何AI客户端可直接对接。

---

## 2. 核心设计原则

| 原则 | 说明 |
|------|------|
| 全对等 | 每个节点功能完整，无角色区分 |
| 自发现 | 节点自动发现彼此，无需配置中心 |
| 渐进扩展 | 从单机到集群，平滑迁移，无需重构 |
| 数据自治 | 每个节点存储部分数据，共同构成完整数据集 |
| 容错 | 节点下线，数据自动迁移，服务不中断 |
| AI原生 | MCP协议对接，AI可直接操作系统 |

---

## 3. 架构演进路线

```
Phase 1: 单节点SQLite (验证功能，2C2G可运行)
    │
    ├── 功能完整，插件系统就绪，MCP就绪
    │
    ▼
Phase 2: 主从复制 (双机高可用，手动切换)
    │
    ├── 异步复制，故障手动切
    │
    ▼
Phase 3: Raft集群 (多节点，自动切换)
    │
    ├── 强一致，自动故障转移
    │
    ▼
Phase 4: 数据分片 (完整分布式)
    │
    └── 数据分散多节点，自动重平衡
```

---

## 4. 技术选型

### 4.1 核心栈 (Python)

| 层级 | 选型 | 理由 |
|------|------|------|
| 运行时 | Python 3.11+ | 生态丰富，开发效率高，插件系统灵活 |
| 框架 | FastAPI | 高性能，异步支持，自动生成OpenAPI |
| 数据库 | SQLite + 预留Raft | 轻量，Phase 1-2足够，Phase 3+可接Raft |
| 分布式共识 | 预留 (python-raft / Go sidecar) | Phase 3实现，前期预留接口 |
| 服务发现 | python-gossip / 自实现 | UDP gossip，节点自发现 |
| 对象存储 | 本地存储 + 节点同步 | 简单可靠 |
| 搜索 | SQLite FTS5 / Whoosh | 嵌入式，无需外部服务 |
| 模板 | Jinja2 | 功能强大，生态成熟 |
| AI对接 | MCP (Model Context Protocol) | 标准协议，任何AI客户端可直接对接 |
| 部署 | Docker / PyInstaller | 打包成单二进制或容器 |

### 4.2 Python vs Go 对比

| 方面 | Python | Go | 说明 |
|------|--------|-----|------|
| 内存占用 | 高 2-3x | 低 | 2C2G更紧张，但可接受 |
| 启动速度 | 慢 | 快 | 冷启动几百ms vs 几十ms |
| 开发效率 | 高 | 中 | Python动态类型，迭代快 |
| 插件系统 | 极灵活 | 复杂 | Python `importlib` 天然支持 |
| Raft库 | 不成熟 | 成熟 | 需权衡：sidecar或后期实现 |
| AI生态 | 极强 | 弱 | Python是AI第一语言 |
| 模板引擎 | Jinja2 | 内置 | Jinja2功能更强 |

### 4.3 Phase对比

| 阶段 | 存储 | 复制 | 切换 | 适用场景 |
|------|------|------|------|----------|
| Phase 1 | SQLite | 无 | - | 单机，验证功能 |
| Phase 2 | SQLite | 异步 | 手动 | 双机，高可用要求低 |
| Phase 3 | SQLite + Raft | Raft | 自动 | 多节点，强一致 |
| Phase 4 | SQLite + Raft + 分片 | Raft | 自动 | 大规模，数据分散 |

---

## 5. 架构图

### 5.1 Phase 1: 单节点 + MCP

```
┌─────────────────────────────────────────────────────────────┐
│                     Node (2C2G)                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────────────┐ │
│  │  FastAPI│  │ SQLite  │  │  Local  │  │  MCP Server    │ │
│  │  (完整) │  │ (全量)  │  │ Storage │  │  (stdio/SSE)   │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └───────┬────────┘ │
│       │            │            │                │          │
│       └────────────┴────────────┴────────────────┘          │
│                        完全体节点                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ MCP协议
                              ▼
                    ┌─────────────────┐
                    │  AI客户端        │
                    │ (Claude/Cursor) │
                    └─────────────────┘
```

### 5.2 Phase 3: Raft集群 + MCP

```
┌─────────────────────────────────────────────────────────────┐
│                     全对等节点集群                           │
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │    Node A (2C2G)    │◄──►│    Node B (2C2G)    │        │
│  │ FastAPI + SQLite +  │    │ FastAPI + SQLite +  │        │
│  │ Raft + Gossip + MCP │    │ Raft + Gossip + MCP │        │
│  └─────────────────────┘    └─────────────────────┘        │
│           ▲                           ▲                     │
│           │         Gossip            │                     │
│           └─────────────┬─────────────┘                     │
│                         │                                   │
│              ┌─────────────────────┐                        │
│              │    Node C (2C2G)    │                        │
│              │ FastAPI + SQLite +  │                        │
│              │ Raft + Gossip + MCP │                        │
│              └─────────────────────┘                        │
│                                                             │
│  - 请求打到任意节点，自动路由                               │
│  - 数据多副本，任一节点故障自动切换                         │
│  - MCP Server每个节点都有，AI可连任意节点                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 存储层抽象设计 (Python)

### 6.1 核心接口

```python
# storage/interface.py
from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict
from dataclasses import dataclass
from contextlib import contextmanager

@dataclass
class RaftIndex:
    term: int
    index: int

@dataclass
class LogEntry:
    index: RaftIndex
    timestamp: int
    op: str  # INSERT | UPDATE | DELETE
    table: str
    record_id: int
    data: bytes  # JSON
    checksum: str

class Engine(ABC):
    """存储引擎抽象接口"""
    
    @abstractmethod
    async def get(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        """读取单条记录"""
        pass
    
    @abstractmethod
    async def put(self, table: str, record_id: int, data: Dict[str, Any]) -> None:
        """写入记录"""
        pass
    
    @abstractmethod
    async def delete(self, table: str, record_id: int) -> None:
        """删除记录"""
        pass
    
    @abstractmethod
    async def query(self, table: str, **filters) -> List[Dict[str, Any]]:
        """条件查询"""
        pass
    
    @contextmanager
    @abstractmethod
    async def transaction(self):
        """事务上下文"""
        pass
    
    # 迁移相关 (Phase 1就实现)
    @abstractmethod
    async def export(self, since: RaftIndex) -> List[LogEntry]:
        """导出增量日志"""
        pass
    
    @abstractmethod
    async def import_entries(self, entries: List[LogEntry]) -> None:
        """导入日志"""
        pass
    
    @abstractmethod
    def current_index(self) -> RaftIndex:
        """当前日志位置"""
        pass
    
    # 生命周期
    @abstractmethod
    async def start(self) -> None:
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        pass
    
    @property
    @abstractmethod
    def mode(self) -> str:
        """引擎模式: sqlite | master | replica | raft"""
        pass
```

### 6.2 三模式实现

| 模式 | 实现类 | 写入方式 | 复制 |
|------|--------|----------|------|
| SQLite | SQLiteEngine | 直接写本地 | 无 |
| Master | MasterEngine | 写本地 + 异步复制 | 异步 |
| Replica | ReplicaEngine | 只读，接收复制 | 接收 |
| Raft | RaftEngine | 走Raft日志 | Raft共识 |

### 6.3 SQLiteEngine (Phase 1)

```python
# storage/sqlite_engine.py
import aiosqlite
import json
from typing import Any, Optional, List, Dict
from .interface import Engine, LogEntry, RaftIndex

class SQLiteEngine(Engine):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._mode = "sqlite"
    
    async def start(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        await self._init_tables()
    
    async def _init_tables(self) -> None:
        """初始化业务表和系统表"""
        # 业务表 (示例)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                author_id INTEGER,
                status TEXT DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                raft_term INTEGER DEFAULT 0,
                raft_index INTEGER DEFAULT 0,
                version INTEGER DEFAULT 1,
                node_id TEXT DEFAULT 'local'
            )
        """)
        
        # Raft日志表 (Phase 1就创建，预留)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS _raft_log (
                term INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                op TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id INTEGER,
                data BLOB,
                checksum TEXT,
                PRIMARY KEY (term, idx)
            )
        """)
        
        # 元数据表
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS _meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await self._db.commit()
    
    async def get(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        async with self._db.execute(
            f"SELECT * FROM {table} WHERE id = ?", (record_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    async def put(self, table: str, record_id: int, data: Dict[str, Any]) -> None:
        # 构建INSERT OR REPLACE
        columns = list(data.keys())
        placeholders = ', '.join(['?' for _ in columns])
        values = [data.get(c) for c in columns]
        
        await self._db.execute(
            f"INSERT OR REPLACE INTO {table} (id, {', '.join(columns)}) VALUES (?, {placeholders})",
            (record_id, *values)
        )
        await self._db.commit()
    
    async def export(self, since: RaftIndex) -> List[LogEntry]:
        """导出增量日志，为迁移准备"""
        async with self._db.execute(
            """SELECT * FROM _raft_log 
               WHERE term > ? OR (term = ? AND idx > ?)
               ORDER BY term, idx""",
            (since.term, since.term, since.index)
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_log_entry(row) for row in rows]
    
    @property
    def mode(self) -> str:
        return self._mode
```

---

## 7. 数据表设计 (Phase 1就要完整)

### 7.1 业务表模板

```sql
-- 所有业务表必须包含这些字段
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    
    -- 业务字段
    title TEXT NOT NULL,
    content TEXT,
    author_id INTEGER,
    status TEXT DEFAULT 'draft',
    
    -- 时间戳
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    
    -- 分布式预留字段 (Phase 1就加，暂时不用)
    raft_term INTEGER DEFAULT 0,
    raft_index INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    node_id TEXT DEFAULT 'local',
    client_seq INTEGER DEFAULT 0
);
```

### 7.2 系统表

```sql
-- Raft日志表 (所有阶段都存在)
CREATE TABLE _raft_log (
    term INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    op TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id INTEGER,
    data BLOB,
    checksum TEXT,
    PRIMARY KEY (term, idx)
);

-- 元数据表
CREATE TABLE _meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### 7.3 核心业务表

```sql
-- 用户
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at INTEGER NOT NULL,
    role TEXT DEFAULT 'user',
    avatar TEXT,
    raft_term INTEGER DEFAULT 0,
    raft_index INTEGER DEFAULT 0
);

-- OAuth绑定
CREATE TABLE user_oauth (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,  -- 'github'|'google'|'wechat'
    provider_id TEXT NOT NULL,
    provider_name TEXT,
    provider_avatar TEXT,
    access_token TEXT,
    refresh_token TEXT,
    expires_at INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE(user_id, provider)
);

-- 内容表 (插件复用)
CREATE TABLE contents (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER,
    plugin_type TEXT NOT NULL,  -- 'blog'|'note'|'microblog'
    author_id INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    meta_json TEXT,
    tags TEXT,  -- JSON数组
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    status TEXT DEFAULT 'draft',
    raft_term INTEGER DEFAULT 0,
    raft_index INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    node_id TEXT DEFAULT 'local'
);

-- 文件对象
CREATE TABLE objects (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER,
    filename TEXT NOT NULL,
    size INTEGER,
    mime_type TEXT,
    storage_path TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    raft_term INTEGER DEFAULT 0,
    raft_index INTEGER DEFAULT 0
);

-- 任务队列
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER,
    plugin_type TEXT NOT NULL,
    title TEXT NOT NULL,
    due_at INTEGER,
    status TEXT DEFAULT 'pending',
    meta_json TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    raft_term INTEGER DEFAULT 0,
    raft_index INTEGER DEFAULT 0
);

-- 插件元数据
CREATE TABLE plugins (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    version TEXT,
    enabled BOOLEAN DEFAULT 1,
    config TEXT,  -- JSON
    node_selector TEXT,
    created_at INTEGER NOT NULL
);
```

---

## 8. MCP集成设计

### 8.1 MCP架构

```
AI 客户端 (Claude Desktop / Cursor / 自定义)
       │
       │ MCP协议 (stdio / SSE)
       ▼
┌─────────────────────────────────────────┐
│           MCP Server                    │
│  ┌─────────────────────────────────┐   │
│  │  Tools (插件操作)                │   │
│  │  - blog.create_post             │   │
│  │  - blog.search_posts            │   │
│  │  - notes.create_note            │   │
│  │  - rss.add_feed                 │   │
│  │  - todo.create_task             │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Resources (内容数据)            │   │
│  │  - blog://posts                 │   │
│  │  - blog://posts/{id}            │   │
│  │  - notes://notes                │   │
│  │  - rss://items                  │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │  Prompts (模板)                  │   │
│  │  - blog-writing-template        │   │
│  │  - meeting-summary-template     │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 8.2 插件MCP接口

```python
# plugin/interface.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable
from dataclasses import dataclass

@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    handler: Callable[..., Any]

@dataclass
class MCPResource:
    """MCP资源定义"""
    uri: str
    name: str
    mime_type: str
    handler: Callable[..., Any]

@dataclass
class MCPPrompt:
    """MCP提示词模板"""
    name: str
    description: str
    template: str
    arguments: List[Dict[str, Any]]  # 模板参数定义

class Plugin(ABC):
    """插件基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        pass
    
    @abstractmethod
    async def init(self, ctx: 'PluginContext') -> None:
        """插件初始化"""
        pass
    
    @abstractmethod
    def routes(self) -> List['Route']:
        """注册HTTP路由"""
        pass
    
    # MCP相关
    def mcp_tools(self) -> List[MCPTool]:
        """返回MCP工具列表"""
        return []
    
    def mcp_resources(self) -> List[MCPResource]:
        """返回MCP资源列表"""
        return []
    
    def mcp_prompts(self) -> List[MCPPrompt]:
        """返回MCP提示词列表"""
        return []
```

### 8.3 Blog插件MCP示例

```python
# plugins/blog/plugin.py
from typing import List, Dict, Any
from plugin.interface import Plugin, MCPTool, MCPResource, MCPPrompt

class BlogPlugin(Plugin):
    @property
    def name(self) -> str:
        return "blog"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="create_post",
                description="创建博客文章",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "文章标题"},
                        "content": {"type": "string", "description": "文章内容(Markdown)"},
                        "status": {"type": "string", "enum": ["draft", "published"], "default": "draft"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "content"]
                },
                handler=self.create_post
            ),
            MCPTool(
                name="search_posts",
                description="搜索博客文章",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "tag": {"type": "string", "description": "标签过滤"},
                        "limit": {"type": "integer", "default": 10}
                    }
                },
                handler=self.search_posts
            ),
            MCPTool(
                name="update_post",
                description="更新博客文章",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "文章ID"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["draft", "published"]}
                    },
                    "required": ["id"]
                },
                handler=self.update_post
            ),
        ]
    
    def mcp_resources(self) -> List[MCPResource]:
        return [
            MCPResource(
                uri="blog://posts",
                name="所有文章列表",
                mime_type="application/json",
                handler=self.list_all_posts
            ),
            MCPResource(
                uri="blog://posts/{id}",
                name="文章详情",
                mime_type="text/markdown",
                handler=self.get_post
            ),
            MCPResource(
                uri="blog://posts/{id}/html",
                name="文章详情(HTML)",
                mime_type="text/html",
                handler=self.get_post_html
            ),
        ]
    
    def mcp_prompts(self) -> List[MCPPrompt]:
        return [
            MCPPrompt(
                name="blog-writing-template",
                description="博客写作模板",
                template="""请根据以下主题撰写一篇博客文章：

主题：{{topic}}
目标读者：{{audience}}
风格：{{style}}

要求：
1. 标题吸引人
2. 结构清晰，有引言、正文、结论
3. 使用Markdown格式
4. 适当使用列表和代码块
""",
                arguments=[
                    {"name": "topic", "description": "文章主题", "required": True},
                    {"name": "audience", "description": "目标读者", "required": False},
                    {"name": "style", "description": "写作风格", "required": False}
                ]
            ),
        ]
    
    async def create_post(self, title: str, content: str, status: str = "draft", tags: List[str] = None) -> Dict[str, Any]:
        """创建文章"""
        # 实现...
        pass
    
    async def search_posts(self, query: str = None, tag: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索文章"""
        # 实现...
        pass
```

### 8.4 MCP Server实现

```python
# mcp/server.py
from mcp.server import Server
from mcp.types import Tool, Resource, Prompt
from typing import List

class WorkbenchMCPServer:
    """工作台MCP服务器"""
    
    def __init__(self, plugin_manager: 'PluginManager'):
        self.server = Server("workbench")
        self.plugin_manager = plugin_manager
        self._register_handlers()
    
    def _register_handlers(self):
        """注册MCP处理器"""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """列出所有可用工具"""
            tools = []
            for plugin in self.plugin_manager.get_enabled_plugins():
                for mcp_tool in plugin.mcp_tools():
                    tools.append(Tool(
                        name=f"{plugin.name}.{mcp_tool.name}",
                        description=mcp_tool.description,
                        inputSchema=mcp_tool.input_schema
                    ))
            return tools
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list:
            """调用工具"""
            plugin_name, tool_name = name.split(".", 1)
            plugin = self.plugin_manager.get_plugin(plugin_name)
            
            for mcp_tool in plugin.mcp_tools():
                if mcp_tool.name == tool_name:
                    result = await mcp_tool.handler(**arguments)
                    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
            
            raise ValueError(f"Tool not found: {name}")
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """列出所有资源"""
            resources = []
            for plugin in self.plugin_manager.get_enabled_plugins():
                for mcp_resource in plugin.mcp_resources():
                    resources.append(Resource(
                        uri=mcp_resource.uri,
                        name=mcp_resource.name,
                        mimeType=mcp_resource.mime_type
                    ))
            return resources
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """读取资源"""
            for plugin in self.plugin_manager.get_enabled_plugins():
                for mcp_resource in plugin.mcp_resources():
                    if mcp_resource.uri == uri:
                        return await mcp_resource.handler()
            raise ValueError(f"Resource not found: {uri}")
    
    async def run(self, transport: str = "stdio"):
        """启动MCP服务器"""
        if transport == "stdio":
            from mcp.server.stdio import stdio_server
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
        elif transport == "sse":
            # SSE transport for web
            pass
```

### 8.5 AI使用示例

```
用户: 帮我写一篇关于Python异步编程的博客

AI: 我来帮你创建这篇文章。首先，让我使用博客写作模板生成内容，然后保存到你的博客中。

[AI调用 MCP Tool: blog-writing-template]
[AI调用 MCP Tool: blog.create_post]

已为你创建博客文章《深入理解Python异步编程》，
标题：深入理解Python异步编程
状态：草稿
链接：http://localhost:8080/blog/123

你可以继续编辑或直接发布。

---

用户: 我最近的博客文章有哪些？

[AI调用 MCP Resource: blog://posts]

你最近有3篇文章：
1. 《深入理解Python异步编程》- 草稿 (2小时前)
2. 《SQLite性能优化指南》- 已发布 (3天前)
3. 《MCP协议入门》- 已发布 (1周前)
```

---

## 9. 前端模板系统

### 9.1 模板目录结构

```
plugins/
├── blog/
│   ├── __init__.py
│   ├── plugin.py
│   └── templates/
│       ├── default/
│       │   ├── layout.html
│       │   ├── post_list.html
│       │   └── post_detail.html
│       └── minimal/
│           ├── layout.html
│           └── post_list.html
├── notes/
│   ├── __init__.py
│   ├── plugin.py
│   └── templates/
│       └── default/
│           ├── layout.html
│           └── note.html
```

### 9.2 模板导入 (ZIP包)

```
my-theme.zip
├── manifest.json
├── preview.png
├── layout.html
├── post_list.html
└── assets/
    ├── style.css
    └── logo.png
```

manifest.json:
```json
{
    "name": "dark-reader",
    "display_name": "Dark Reader",
    "version": "1.0.0",
    "author": "zhangsan",
    "plugin_types": ["blog", "notes"],
    "preview": "preview.png",
    "config": {
        "primary_color": "#1890ff",
        "font_family": "sans-serif"
    }
}
```

### 9.3 渲染引擎 (Jinja2)

```python
# template/engine.py
from jinja2 import Environment, FileSystemLoader, PackageLoader
from typing import Dict, Any, Optional
import os

class TemplateEngine:
    def __init__(self, plugin_manager: 'PluginManager'):
        self.plugin_manager = plugin_manager
        self.env = Environment(
            loader=PackageLoader('app', 'templates'),
            autoescape=True  # 自动转义，防XSS
        )
        self.custom_templates: Dict[str, Environment] = {}
    
    def render(
        self,
        plugin_type: str,
        template_name: str,
        page: str,
        data: Any,
        config: Optional[Dict[str, Any]] = None,
        site_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """渲染模板"""
        # 1. 查找模板
        template_path = f"{plugin_type}/{template_name}/{page}.html"
        
        # 2. 注入通用变量
        context = {
            'Site': site_config or {},
            'Config': config or {},
            'Plugin': plugin_type,
            'User': None,  # 当前用户
            'CSRF': '',    # CSRF token
            'Assets': {},  # 静态资源映射
            **data
        }
        
        # 3. 渲染
        template = self.env.get_template(template_path)
        return template.render(**context)
```

### 9.4 模板语法 (Jinja2)

```html
<!-- layout.html -->
<!DOCTYPE html>
<html>
<head>
    <title>{{ Site.name }} - {% block title %}{% endblock %}</title>
    <style>
        :root { --primary: {{ Config.primary_color }}; }
    </style>
    {% block head %}{% endblock %}
</head>
<body class="theme-{{ Config.theme }}">
    {% block content %}{% endblock %}
</body>
</html>

<!-- post_list.html -->
{% extends "layout.html" %}
{% block title %}博客列表{% endblock %}
{% block content %}
<div class="posts">
    {% for post in Posts %}
    <article>
        <h2><a href="/blog/{{ post.id }}">{{ post.title }}</a></h2>
        <time>{{ post.created_at | format_date }}</time>
        <p>{{ post.content | truncate(200) }}</p>
    </article>
    {% endfor %}
</div>
{% endblock %}
```

---

## 10. 部署方案

### 10.1 单节点 (Phase 1)

```bash
# 方式1: 直接运行
python -m app \
  --node-id node-1 \
  --http :8080 \
  --data-dir ./data \
  --mcp-stdio  # 启用MCP stdio模式

# 方式2: Docker
docker run -d \
  -v ./data:/data \
  -p 8080:8080 \
  myapp:latest \
  --node-id node-1 \
  --http :8080 \
  --data-dir /data
```

### 10.2 MCP配置 (Claude Desktop)

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "workbench": {
      "command": "python",
      "args": [
        "-m", "app",
        "--node-id", "node-1",
        "--data-dir", "./data",
        "--mcp-stdio"
      ],
      "env": {
        "PYTHONPATH": "/path/to/app"
      }
    }
  }
}
```

### 10.3 2C2G资源分配 (Python)

```
2C2G 节点资源分配 (Python):
├─ OS:                200MB
├─ Python运行时:      150MB
├─ FastAPI + 依赖:    200MB
├─ SQLite (缓存):     300MB
├─ Whoosh索引:        150MB
├─ Gossip/预留Raft:   100MB
├─ 文件存储缓存:       200MB
└─ 剩余:              ~700MB (OS缓存)

Python比Go多占约300-400MB内存，2C2G仍可运行，但余量更小。
```

---

## 11. 配置设计

```yaml
# config.yaml
app:
  name: "workbench"
  debug: false

storage:
  mode: sqlite  # sqlite | master | replica | raft
  
  sqlite:
    path: ./data/app.db
    wal_mode: true
    
  replication:
    role: master
    peers: []
    sync_interval: 100ms
    
  raft:
    node_id: "node-1"
    bind_addr: "0.0.0.0:12000"
    data_dir: ./data/raft
    join: []
    snapshot_interval: 10000

http:
  addr: "0.0.0.0:8080"
  cors_origins: ["*"]

mcp:
  enabled: true
  transport: stdio  # stdio | sse
  
plugins:
  enabled: [blog, notes, todo, rss]
  dir: ./plugins
  
logging:
  level: info
  format: json
```

---

## 12. 实现优先级

### P0 (Phase 1 必须)
1. FastAPI框架搭建
2. 存储层抽象接口 (Python async)
3. SQLiteEngine实现
4. 业务表设计 (含预留字段)
5. _raft_log表
6. 插件系统框架 (importlib)
7. MCP Server框架
8. 模板渲染引擎 (Jinja2 + 内置模板)

### P1 (Phase 2)
1. MasterEngine / ReplicaEngine
2. 异步复制通道 (WebSocket/HTTP)
3. 复制延迟监控
4. 模板导入功能 (ZIP上传)
5. 更多MCP Tools

### P2 (Phase 3)
1. RaftEngine实现 (python-raft或sidecar)
2. 快照/恢复
3. 迁移协调器
4. MCP Resources完整实现

### P3 (Phase 4)
1. 数据分片
2. 自动重平衡
3. 跨节点查询优化

---

## 13. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Python内存占用高 | 2C2G紧张 | 精简依赖，控制并发，必要时升级4C4G |
| Raft库不成熟 | Phase 3受阻 | 预留接口，可用Go sidecar方案兜底 |
| 冷启动慢 | 用户体验差 | 用uvloop，预加载关键模块 |
| MCP协议变更 | 兼容性问题 | 锁定版本，抽象MCP层 |
| 模板XSS | 安全风险 | Jinja2 autoescape，用户输入过滤 |
| GIL限制 | CPU密集型任务阻塞 | 用进程池，或拆分到独立服务 |

---

## 14. 文档索引

| 文档 | 内容 |
|------|------|
| `2026-04-16-design-summary.md` | 本文档，Python + MCP 完整设计（主文档） |

---

**结论**:
- Python开发效率高，AI生态强，MCP集成顺畅
- 内存占用比Go高，2C2G仍可运行但余量小
- Phase 1-2完全可行，Phase 3 Raft需评估python-raft成熟度或考虑sidecar方案
- MCP协议让AI直接操作系统，无需额外适配层
