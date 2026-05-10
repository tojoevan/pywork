# pyWork 代码审视报告

> 审查日期：2026-05-10 | 审查范围：全量代码（app/ + plugins/ + templates/ + tests/）

## 项目概述

pyWork 是一个基于 FastAPI + SQLite 的多用户数字工作台，采用插件化架构，集成 MCP 协议供 AI Agent 交互。代码量约 12,000+ 行 Python，包含 10 个功能插件。

---

## 一、安全问题（P0 — 紧急）

### 1.1 XSS 搜索高亮注入 ✅ 已修复

**文件**: `app/main.py:900-903`, `plugins/blog/plugin.py:370-372`

`_highlight_excerpt` 和 `_highlight_text` 方法将用户搜索关键词直接拼接进 HTML，未做 HTML 转义：

```python
# 当前代码（有漏洞）
text = pattern.sub(lambda m: f'<span class="highlight">{m.group()}</span>', text)
```

攻击者搜索 `<img src=x onerror=alert(1)>` 即可注入恶意脚本到搜索结果页面。

**修复建议**:

```python
from markupsafe import escape
text = pattern.sub(lambda m: f'<span class="highlight">{escape(m.group())}</span>', text)
```

### 1.2 Cookie 缺少安全属性 ✅ 已修复

**文件**: `plugins/auth/plugin.py:794-799`, `app/main.py:482-487`

`auth_token` Cookie 未设置 `Secure`、`SameSite` 属性：

```python
# 当前代码
response.set_cookie(key="auth_token", value=token, httponly=True, max_age=7*24*3600)

# 建议修改
response.set_cookie(
    key="auth_token", value=token,
    httponly=True, secure=True, samesite="lax",
    max_age=7*24*3600
)
```

**风险**: 非 HTTPS 环境下 Cookie 可被中间人窃取；缺少 `SameSite` 易受 CSRF 攻击。

### 1.3 GitHub OAuth State 未验证 ✅ 已修复

**文件**: `plugins/auth/plugin.py:314-361`

`github_callback` 接收 `state` 参数但从未验证其合法性。OAuth 流程中 `state` 的作用是防止 CSRF 攻击，当前实现完全无效。

**修复建议**: 授权前将 `state` 存入 session/数据库，回调时校验一致性。

### 1.4 LLM API Key 明文存储 ✅ 已修复

**文件**: `plugins/llm_config/plugin.py`, `app/crypto.py`（新建）

`llm_configs` 表中 `api_key` 以明文存储。数据库泄露将导致所有 LLM API Key 泄露。

**修复方案**: 使用 `cryptography.fernet` 对称加密，`SECRET_KEY` 派生自 `site_config` 并自动持久化。写入时加密（`fernet:` 前缀），读取时解密，启动时自动迁移已有明文密钥（幂等）。

### 1.5 MCP Token 明文存储 ✅ 已修复

**文件**: `plugins/auth/plugin.py`, `app/crypto.py`

MCP Token 以明文存储在 `mcp_tokens` 表中。

**修复方案**: 使用 SHA-256 哈希存储 token（`sha256:hex` 格式），新增 `token_prefix` 列用于显示。创建时仅返回完整 token 一次，验证时哈希比对，启动时自动迁移已有明文 token（幂等）。

### 1.6 MCP 端点无速率限制 ✅ 已修复

**文件**: `app/main.py:568-590`

`/mcp` 端点无任何速率限制，而 `/search` 有 IP 级 30 秒限制。攻击者可通过 MCP 端点暴力枚举 Token 或进行 DoS。

### 1.7 RSS Feed XML 注入 ℹ️ 无需修复

ElementTree.SubElement().text 自动转义 XML 特殊字符，不存在注入风险。

**文件**: `app/main.py:254-273`

RSS 生成使用 `xml.etree.ElementTree`，但 `item["description"]` 包含用户原始内容（博客正文、微博），未做 XML 转义，可能导致 XML 注入或格式破坏。

### 1.8 无 CSRF 保护 ⏭ 待处理

SameSite="lax" 已缓解大部分 CSRF 风险。完整 CSRF Token 方案需后续评估。

所有 POST 端点（登录、注册、评论、博客创建等）均无 CSRF Token 验证。虽然 Cookie 设了 `httponly`，但未设 `SameSite`，仍存在 CSRF 风险。

**README 声明与实际差异**: README 安全设计章节声称"状态修改操作要求用户已登录"作为 CSRF 防护，但仅要求登录并不能防止 CSRF 攻击。

---

## 二、代码质量问题（P1）

### 2.1 大量裸 `except` 捕获 ✅ 已修复

全项目存在 **20+ 处** 裸 `except:` 或 `except Exception` 吞掉所有异常且不记录日志：

**修复方案**: 将裸 `except:` 替换为具体异常类型：
- ALTER TABLE 迁移 → `except Exception`（字段已存在是预期行为）
- JSON 解析 → `except (json.JSONDecodeError, TypeError)`
- 密码解析 → `except (ValueError, TypeError, KeyError)`
- 请求体解析 → `except Exception`
- 字体加载 → `except (OSError, IOError)`
- 网络探测 → `except Exception`

### 2.2 高亮函数重复实现 ✅ 已修复

提取为 `app/utils.py:highlight_excerpt()`，两处调用方已更新。

### 2.3 默认 `author_id=1` 硬编码 ✅ 已修复

blog/topic 改为必填，未登录拒绝操作。microblog 匿名发布使用 `author_id=0`（非真实用户）。

### 2.4 HomeService 全量加载后过滤 ✅ 已修复

blog/microblog/notes 的 `list_posts`/`list_notes` 已支持 `author_id` 参数，HomeService 直接在 SQL 层过滤。

### 2.5 函数体内重复 `import` ✅ 已修复

多处在函数内部重复 `import` 已在顶层导入的模块：

- `plugins/auth/plugin.py:64` — `import time`（顶层已导入）
- `plugins/auth/plugin.py:245, 349, 509` — 多次 `import time`
- `app/main.py:609, 900` — `import time`, `import re`

### 2.6 `engine.execute()` 自动 commit ✅ 已修复

**文件**: `app/storage/sqlite_engine.py:725-728`, `plugins/board/plugin.py`

`execute()` 每次调用都 auto-commit，批量操作（`_handle_hot_tags` 清空+重写、`_handle_recent_comments` 清空+重写）无法保证原子性。

**修复方案**: 引擎已有 `transaction()` 上下文管理器，将批量操作包裹在 `async with self.engine.transaction()` 中，确保 DELETE + INSERT 原子执行。

### 2.7 魔术 Mock Request 对象 ✅ 已修复

改为直接传递 `state` 参数，不再创建伪 Request 对象。

---

## 三、架构问题（P2）

### 3.1 缓存一致性 ⏭ 待处理

**文件**: `app/template/engine.py:240-267` vs `app/config.py:114-147`

`TemplateEngine._site_cache` 和 `SiteConfigManager._cache` 是两套独立缓存：

| 缓存 | TTL | 清除时机 |
|------|-----|---------|
| `TemplateEngine._site_cache` | 无 TTL（永久） | 手动 `_site_cache = None` |
| `SiteConfigManager._cache` | 30 秒 | `set()`/`batch_set()` 时清除 |

更新设置时需手动清除两个缓存，容易遗漏导致页面显示旧数据。

**修复方案**: TemplateEngine 新增 `site_config_manager` 参数，优先使用 SiteConfigManager 加载配置（统一缓存源）。WorkbenchApp 创建 TemplateEngine 时传入 site_config_manager。

### 3.2 PluginManager 内部属性外部访问 ✅ 已修复

改为公开属性 `template_engine`，通过赋值注入。

### 3.3 FastAPI 生命周期弃用 ✅ 已修复

已迁移到 `lifespan` 上下文管理器。

### 3.4 日志 SQLite Handler 异步问题 ⏭ 待处理

**文件**: `app/log.py:94-101`

```python
loop.create_task(self._write(entry))
```

在 logging `emit()` 中创建 asyncio Task，如果事件循环已满或正在关闭，日志会静默丢失。

### 3.5 SQL 构建中 f-string 使用 ⏭ 待处理

**文件**: `plugins/board/plugin.py:1313-1316`

```python
rows = await self.engine.fetchall(
    f"SELECT ... FROM app_logs WHERE {where_clause} ORDER BY {order_clause} LIMIT ? OFFSET ?",
    params + [limit, offset],
)
```

虽然 `where_clause` 和 `order_clause` 由代码内部控制，但使用 f-string 构建 SQL 是不良实践。`SQLiteEngine.execute()` 不验证原始 SQL，仅 `get/put/delete/query` 有白名单保护。

### 3.6 双虚拟环境 ℹ️ 已记录

`.venv/` 和 `venv/` 都存在且已在 `.gitignore` 中。建议手动删除多余的 `venv/` 目录。

---

## 四、性能问题（P2）

### 4.1 缺少数据库索引 ✅ 已修复

| 表 | 缺失索引 | 影响 |
|----|---------|------|
| `sessions` | `expires_at` | 过期清理全表扫描 |
| `sessions` | `user_id` | 按用户查询 session 慢 |
| `mcp_tokens` | `user_id` | 按用户列出 token 慢 |
| `comments` | `created_at` | 最新评论排序慢 |

**修复方案**: 在 `_init_sessions_table()` 和 `_init_mcp_tokens_table()` 中添加对应索引，comments 表在 `_DDL_COMMENTS` 中添加 `idx_comments_created_at` 索引。

### 4.2 内存型速率限制不可扩展

**文件**: `app/main.py:602-603`, `plugins/microblog/plugin.py:19`

搜索和微博的速率限制存储在进程内存中。重启丢失，多实例部署无效。建议迁移到 SQLite 或 Redis。

### 4.3 验证码内存存储无清理

**文件**: `plugins/auth/plugin.py:21`

`captcha_codes` 存在内存中，无定期清理机制。长时间运行会积累过期数据（虽然每条仅 5 字节，但无上限）。

**建议**: 在 `_verify_captcha` 中添加批量过期清理，或使用 TTL 缓存库。

---

## 五、README 文档问题

### 5.1 安全设计声明不完整

README 声明的安全防护与实际代码存在差距：

| README 声明 | 实际情况 |
|-------------|---------|
| "CSRF：状态修改操作要求用户已登录" | 仅要求登录不能防 CSRF，缺少 Token 验证 |
| "XSS：Markdown 渲染前做 HTML 白名单过滤" | Markdown 渲染有过滤，但搜索高亮存在 XSS |
| "SQL 注入：表名白名单 + 参数化查询" | `board` 插件存在 f-string SQL 构建 |

### 5.2 插件列表不完整

README "内置插件"表格仅列出 6 个插件，实际有 10 个。缺少：`comments`、`llm_config`、`topic`、`nav`。

### 5.3 目录结构过时

README 目录结构中 `plugins/` 仅列出 6 个插件目录，缺少 `comments/`、`llm_config/`、`topic/`、`nav/`。

### 5.4 上次审查总结需更新

README 中"代码审查总结"章节（2026-04-20 ~ 2026-04-22）记录了 23 个已修复问题和 117 个测试用例。本次审查发现的新问题未反映在其中，建议更新该章节或在本文件中持续追踪。

---

## 六、测试覆盖不足

### 6.1 覆盖缺口

| 模块 | 测试状态 |
|------|---------|
| `app/storage/` | 有测试（test_storage.py） |
| `plugins/blog/` | 有测试（test_blog.py, test_plugins.py） |
| `plugins/auth/` | 有测试（test_auth.py） |
| `plugins/microblog/` | 有测试（test_plugins.py） |
| `app/services/home_service.py` | 有测试（test_home_service.py） |
| `app/mcp/server.py` | 有测试（test_mcp.py） |
| `plugins/comments/` | **无测试** |
| `plugins/topic/` | **无测试** |
| `plugins/llm_config/` | **无测试** |
| `plugins/nav/` | **无测试** |
| `plugins/about/` | **无测试** |
| `plugins/board/` | **无测试** |
| `app/template/engine.py` | **无测试** |
| `app/config.py` | **无测试** |
| 安全功能（XSS/CSRF/OAuth） | **无测试** |

### 6.2 根目录临时脚本 ✅ 已清理

13 个临时调试脚本已删除（test_*.py, debug_*.py, check_*.py, analyze_*.py, save_*.py）。

---

## 七、改进建议优先级

| 优先级 | 问题 | 状态 | 影响 | 工作量 |
|--------|------|------|------|--------|
| **P0** | XSS 搜索高亮注入 | ✅ 已修复 | 可被直接利用 | 小 |
| **P0** | Cookie 安全属性 + SameSite | ✅ 已修复 | 会话劫持/CSRF | 小 |
| **P0** | OAuth State 未验证 | ✅ 已修复 | CSRF 攻击 | 中 |
| **P0** | LLM API Key 明文存储 | ✅ 已修复 | 数据泄露 | 中 |
| **P0** | MCP Token 明文存储 | ✅ 已修复 | 数据泄露 | 中 |
| **P1** | MCP 端点无速率限制 | ✅ 已修复 | 暴力破解 | 小 |
| **P1** | 裸 except 捕获 | ✅ 已修复 | 错误隐藏 | 中 |
| **P1** | 搜索高亮代码重复 | ✅ 已修复 | 维护成本 | 小 |
| **P1** | engine.execute() 自动 commit | ✅ 已修复 | 数据一致性 | 中 |
| **P2** | 缓存一致性 | ✅ 已修复 | 数据不同步 | 中 |
| **P2** | 缺少数据库索引 | ✅ 已修复 | 性能瓶颈 | 小 |
| **P2** | FastAPI 生命周期迁移 | ✅ 已修复 | 未来兼容性 | 小 |
| **P3** | 测试覆盖 | ⏭ 待处理 | 回归风险 | 大 |
| **P3** | README 文档同步 | ⏭ 待处理 | 文档准确性 | 小 |
| **P3** | 根目录临时脚本清理 | ✅ 已清理 | 项目整洁 | 小 |

---

## 八、总结

pyWork 的插件化架构设计清晰，MCP 集成思路先进，整体代码质量良好。主要风险集中在：

1. **安全层面** — XSS 高亮注入、Cookie 安全属性缺失、OAuth CSRF（密钥明文存储已全部修复）
2. **代码健壮性** — 缓存不一致、f-string SQL（裸 except 已修复）
3. **测试覆盖** — 10 个插件中仅 3 个有测试，安全功能无测试

建议优先修复 P0 安全问题（预计 1-2 天工作量），再逐步改善代码质量和测试覆盖。
