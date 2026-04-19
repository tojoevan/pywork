# pyWork 多用户数字工作台

## 是什么

一个基于插件架构的多用户数字工作台，使用 Python + FastAPI + SQLite 构建，集成 MCP 协议供 AI 助手直接调用。

目标：让 AI 能够像人类一样操作系统中的内容——写博客、发微博、整理笔记、管理任务。

## 核心特性

**插件架构** — 每个功能模块（博客、微博、笔记、留言板、看板等）都是独立插件，目录即插即用，无需修改核心代码。

**AI 原生** — 通过 MCP 协议（Model Context Protocol）对外暴露所有能力，任何兼容 MCP 的 AI 客户端（Claude Desktop、Cursor 等）可直接调用工具读写工作台内容。

**多用户支持** — 完整用户体系：注册/登录、Session 认证、GitHub OAuth、MCP API Token。

**渐进式架构** — 从单机 SQLite 起步，表结构预留分布式字段，平滑演进到 Raft 集群。

## 内置插件

| 插件 | 说明 |
|------|------|
| `blog` | 博客，Markdown 编辑器（vditor）、标签、搜索 |
| `auth` | 认证：注册/登录/登出、GitHub OAuth、MCP Token |
| `microblog` | 微博，支持匿名发布（需管理员审核后显示） |
| `about` | 留言板，访客留言 + 管理员审核 |
| `notes` | 笔记，公开/私有，Markdown 支持 |
| `board` | 看板（管理员）、定时任务（统计）、网站设置 |

## 页面布局

三栏首页，左侧活跃作者 + 热门标签，中间文章流，右侧公告 + 统计。

```
┌──────────────────────────────────────────────┐
│  pyWork     博客  笔记  关于       [登录]    │
├────────┬──────────────────────┬─────────────┤
│活跃作者│                      │ 公告        │
│热门标签│   文章卡片流          │ 统计        │
│        │                      │             │
├────────┴──────────────────────┴─────────────┤
│           © 2026 pyWork                     │
└──────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 运行时 | Python 3.11+ |
| Web 框架 | FastAPI + uvicorn |
| 数据库 | SQLite（aiosqlite，WAL 模式）|
| 模板引擎 | Jinja2（异步）|
| AI 协议 | MCP（Model Context Protocol）|
| 编辑器 | vditor 3.10.4（Markdown）|

## 快速开始

```bash
cd pyWork

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .

# 启动
python -m app.main --http --port 8080
```

访问 http://localhost:8080，第一个注册用户自动成为管理员。

## 目录结构

```
pyWork/
├── app/                      # 核心应用
│   ├── main.py               # 入口，支持 --http 和 --mcp-stdio 两种模式
│   ├── storage/              # 存储引擎（SQLiteEngine，含 Raft 预留字段）
│   ├── plugin/               # 插件接口（Plugin 基类、MCP 工具/资源/提示词定义）
│   ├── template/             # Jinja2 模板引擎（异步、多目录加载、过滤器）
│   └── mcp/                  # MCP Server（Tools/Resources/Prompts）
├── plugins/                  # 插件目录
│   ├── blog/                 # 博客插件（vditor 编辑器、MCP 工具）
│   ├── auth/                 # 认证插件（Session、GitHub OAuth、MCP Token）
│   ├── microblog/            # 微博插件（匿名发布+审核）
│   ├── about/                # 留言板插件（访客留言+审核）
│   ├── notes/                # 笔记插件（公开/私有）
│   └── board/                # 看板插件（任务、定时任务、设置）
├── templates/                # 公共模板（base.html、home.html）
├── static/                   # 静态资源（CSS）
└── data/                     # 数据目录（SQLite 数据库）
```

## MCP 集成

在 AI 助手的 MCP 配置中添加：

```bash
python -m app.main --mcp-stdio
```

调用博客工具示例：

```
用户：帮我写一篇关于 Python 异步编程的博客
AI → MCP Tool: blog.create_post(title="...", content="...")
AI → 返回已创建的文章链接
```

## 分布式演进路线

```
Phase 1  单节点 SQLite       ← 当前实现
Phase 2  主从异步复制        ← 预留接口
Phase 3  Raft 多节点集群     ← 表结构已预留字段
Phase 4  数据分片            ← 存储层已抽象
```

所有业务表已包含 `raft_term`、`raft_index`、`version`、`node_id` 预留字段，迁移无需重构。

## 详细文档

- [部署文档](DEPLOY.md) — 完整部署指南、API 参考、MCP 配置
- [设计文档](doc/2026-04-16-design-summary.md) — 架构设计、技术选型、分布式演进
- [开发日志](doc/) — 各模块开发记录
