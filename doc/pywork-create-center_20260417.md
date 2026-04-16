# pyWork 创作中心功能开发

## 时间
2026-04-17 01:30 GMT+8

## 目标
在用户中心增加创作功能区，支持新建博客等模块内容

## 完成内容

### 1. 用户中心功能区
- 在 profile.html 添加"创作中心"区域
- 三个操作卡片：写博客、写笔记（敬请期待）、发布微动态（敬请期待）
- 灰色+活力绿配色，与首页风格一致

### 2. 新建博客页面
- 创建 `/blog/new` 路由
- 使用 vditor Markdown 编辑器（CDN 引入）
- 功能：
  - 标题输入
  - 标签输入（逗号分隔）
  - 状态选择（草稿/发布）
  - 自动保存（本地 localStorage，30秒间隔）
  - 字数统计
  - 发布后跳转到文章详情页

### 3. 后端支持
- 添加 `new_post_page` 方法渲染页面
- 修改 `create_post_api` 支持：
  - body → content 字段映射
  - 从 Cookie 获取当前用户作为 author_id
- 修改 `_register_route` 传递 request 参数给 handler
- 修复所有 handler 方法签名以接受 request 参数

## 文件变更
- `pyWork/plugins/auth/templates/profile.html` - 添加创作中心功能区
- `pyWork/plugins/blog/templates/new.html` - 新建博客页面（13676 bytes）
- `pyWork/plugins/blog/plugin.py` - 添加 new_post_page 方法，修改 handler 签名
- `pyWork/app/main.py` - _register_route 传递 request 参数

## 测试
- ✅ 博客列表 API 正常
- ✅ 用户中心功能区显示正常
- ✅ 新建博客页面访问正常
- ✅ 发布博客 API 正常

## 访问
- 用户中心：http://localhost:8080/profile
- 新建博客：http://localhost:8080/blog/new
