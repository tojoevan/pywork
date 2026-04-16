# pyWork 前端模板系统开发

**时间**: 2026-04-17 00:30

---

## 目标

为 pyWork 创建前端模板系统，支持：
- 基础模板框架
- 博客前端页面
- Markdown 渲染
- 静态资源服务

---

## 完成内容

### 1. 模板文件

| 文件 | 说明 |
|------|------|
| `templates/base.html` | 基础布局模板 |
| `plugins/blog/templates/index.html` | 博客首页 |
| `plugins/blog/templates/post.html` | 文章详情 |

### 2. 静态资源

| 文件 | 说明 |
|------|------|
| `static/css/base.css` | 基础样式 (3KB)|
| `static/css/blog.css` | 博客样式 (3.8KB) |
| `static/js/base.js` | 基础脚本 (4.3KB) |

### 3. 模板引擎更新

**`app/template/engine.py`**:

- ✅ 自定义过滤器:
  - `datetime` - ISO 格式时间
  - `datefmt` - 友好时间格式（X分钟前）
  - `excerpt` - 摘要提取
  - `markdown` - Markdown → HTML

- ✅ 多目录加载:主模板 + 插件模板
- ✅ 异步渲染支持 (`render_async`)

### 4. FastAPI 路由更新

**`app/main.py`**:

- ✅ `/blog` - 博客首页（HTML 渲染）
- ✅ `/blog/posts/{id}` - 文章详情（Markdown 渲染）
- ✅ 静态文件服务 `/static/*`
- ✅ 模板引擎初始化

### 5. 插件修复

**`plugins/blog/plugin.py`**:

- `get_post_api()` 添加 tags JSON 解析

---

## 测试结果

```bash
# 博客首页
$ curl http://localhost:8080/blog
# 返回完整 HTML，包含导航、文章列表、页脚

# 文章详情
$ curl http://localhost:8080/blog/posts/1
# 返回文章详情，Markdown 正确渲染为 HTML
```

---

## 关键修复

### 问题 1: asyncio.run() 嵌套错误

**原因**: Jinja2 async 模式在 FastAPI 异步环境中调用 `render()`

**解决**: 将 `render()` 改为`async def render()`，使用 `render_async()`

### 问题 2: 字段名不匹配

**原因**: 数据库字段 `body` vs 模板字段 `content`

**解决**: 更新模板使用 `post.body`

### 问题 3: Markdown 被转义

**原因**: Jinja2 autoescape 转义了 HTML 输出

**解决**: 使用 `markupsafe.Markup` 标记为安全 HTML

### 问题 4: Tags 未解析

**原因**: `get_post_api()` 返回原始数据，未解析 JSON

**解决**: 添加 `json.loads(post["tags"])`

---

## 文件结构

```
pyWork/
├── templates/
│   └── base.html
├── static/
│   ├── css/
│   │   ├── base.css
│   │   └── blog.css
│   └── js/
│       └── base.js
├── plugins/blog/templates/
│   ├── index.html
│   └── post.html
└── app/
    ├── main.py(更新)
    └── template/
        └── engine.py (更新)
```

---

## 下一步

1. 添加用户认证页面（登录/注册）
2. 添加文章编辑页面
3. 添加笔记、待办等其他插件前端
4. 优化 CSS 响应式设计
5. 添加代码高亮样式

---

## 参考链接

- Jinja2 文档: https://jinja.palletsprojects.com/
- FastAPI 静态文件: https://fastapi.tiangolo.com/tutorial/static-files/
- Markdown 扩展: https://python-markdown.github.io/extensions/
