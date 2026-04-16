# pyWork GitHub OAuth 认证

**时间**: 2026-04-17 00:58

---

## 目标

完成 GitHub OAuth 认证，支持 GitHub 登录。

---

## 完成内容

### 1. OAuth 功能

**文件**: `plugins/auth/plugin.py`

新增方法：
- `get_github_auth_url()` - 生成 GitHub 授权 URL
- `github_callback()` - 处理 OAuth 回调
- `_exchange_github_code()` - code 换取 access_token
- `_get_github_user()` - 获取 GitHub 用户信息
- `_find_or_create_github_user()` - 查找或创建用户

### 2. API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/auth/github` | GET | 跳转 GitHub 授权 |
| `/auth/github/callback` | GET | OAuth 回调处理 |

### 3. 数据库更新

```sql
ALTER TABLE users ADD COLUMN github_id TEXT;
```

### 4. 依赖更新

```toml
# pyproject.toml
"aiohttp>=3.9.0"  # HTTP 客户端
```

---

## GitHub OAuth 配置

### 步骤 1: 创建 GitHub OAuth App

1. 访问 https://github.com/settings/developers
2. 点击 "New OAuth App"
3. 填写信息：
   - **Application name**: pyWork
   - **Homepage URL**: http://localhost:8080
   - **Authorization callback URL**: http://localhost:8080/auth/github/callback
4. 创建后获取 `Client ID`
5. 生成 `Client Secret`

### 步骤 2: 配置环境变量

```bash
# 方式一：命令行
export GITHUB_CLIENT_ID="your_client_id"
export GITHUB_CLIENT_SECRET="your_client_secret"
export GITHUB_REDIRECT_URI="http://localhost:8080/auth/github/callback"

# 方式二：创建 .env 文件
cat > .env << 'EOF'
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:8080/auth/github/callback
EOF

# 启动时加载
source .env && python -m app.main --http
```

### 步骤 3: 测试

```bash
# 访问登录页面
open http://localhost:8080/login

# 点击 GitHub 按钮
# 或直接访问
open http://localhost:8080/auth/github
```

---

## OAuth 流程

```
用户浏览器pyWork服务器GitHub API
    ││                   │
    │ 1. 点击 GitHub 登录││
    ├──────────────────>││
    │                   │ │
    │ 2. 302 重定向到 GitHub│
    │<──────────────────┤│
    │                   │ │
    │ 3. 用户授权││
    ├─────────────────────────────>│
    ││                   ││
    │ 4. 回调 ?code=xxx ││
    │<─────────────────────────────┤
    ││                   ││
    ││ 5. code → access_token│
    ││                   ├────────────>│
    ││                   ││
    ││ 6. 获取用户信息││
    ││                   │<────────────┤
    ││                   ││
    │ 7. 设置 Cookie 登录││
    │<──────────────────┤│
    │                   │ │
```

---

## 用户关联逻辑

1. 通过 `github_id` 查找已绑定用户
2. 通过 `email` 查找已有用户，更新 `github_id`
3. 创建新用户：
   - username = GitHub login
   - email = GitHub email（优先主邮箱）
   - avatar = GitHub avatar_url

---

## 安全考虑

- 使用 `state` 参数防止 CSRF
- Access token 仅用于获取用户信息，不存储
- Session token 使用 HTTP-Only Cookie
- 回调 URL 必须完全匹配 GitHub OAuth App 配置

---

## 测试结果

```bash
# 未配置时
$ curl http://localhost:8080/auth/github
{"error": "GitHub OAuth 未配置"}

# 已配置时（需要真实 OAuth App）
# 会返回 302 重定向到 GitHub 授权页面
```

---

## 文件变更

```
pyWork/
├── plugins/auth/plugin.py (更新, +140行)
├── app/main.py (更新, +36行)
├── pyproject.toml (更新, +1行)
└── data/pywork.db (更新, +1字段)
```

---

## 下一步

1. **生产部署**:
   - 使用 HTTPS
   - 更新回调 URL 为生产域名
   - 使用环境变量或密钥管理服务

2. **功能增强**:
   - 添加 Google OAuth
   - 支持多 OAuth 提供商绑定同一账号
   - OAuth 登录后要求设置密码（可选）

3. **安全增强**:
   - 添加 PKCE 支持
   - Session 过期处理
   - 登录日志记录
