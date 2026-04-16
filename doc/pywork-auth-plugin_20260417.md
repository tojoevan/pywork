# pyWork 登录插件开发

**时间**: 2026-04-17 00:44

---

## 目标

完成登录插件与页面，实现用户认证系统。

---

## 完成内容

### 1. 认证插件

**文件**: `plugins/auth/plugin.py`

功能：
- 用户注册 (`register`)
- 用户登录 (`login`)
- 用户登出 (`logout`)
- 获取用户信息 (`get_user`, `get_user_by_token`)
- 密码修改 (`change_password`)

安全特性：
- PBKDF2-SHA256 密码哈希
- 100000次迭代
- 随机盐值
- Session token (URL-safe, 32字节)

### 2. 前端页面

**登录页面**: `plugins/auth/templates/login.html`
- 用户名/密码登录表单
- "记住我"选项
- 忘记密码链接
- 社交登录按钮 (GitHub/Google)
- 注册链接

**注册页面**: `plugins/auth/templates/register.html`
- 用户名/邮箱/密码表单
- 密码确认
- 服务条款同意
- 登录链接

### 3. 样式

**文件**: `static/css/auth.css`

- 灰色+活力绿配色（与首页一致）
- 居中卡片布局
- 表单样式
- 按钮交互效果
- 响应式设计

### 4. API路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/login` | GET | 登录页面 |
| `/register` | GET | 注册页面 |
| `/auth/login` | POST | 登录API |
| `/auth/register` | POST | 注册API |
| `/auth/logout` | POST | 登出API |
| `/auth/me` | GET | 当前用户信息 |

### 5. MCP工具

认证插件提供以下MCP工具：
- `auth_register` - 用户注册
- `auth_login` - 用户登录
- `auth_logout` - 用户登出
- `auth_get_user` - 获取用户信息

---

## 测试结果

```bash
# 注册
$ curl -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"user4","email":"user4@example.com","password":"pass1234"}'
  
响应: {"success":true,"user":{"id":4,"username":"user4",...}}

# 登录
$ curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user4","password":"pass1234"}'
  
响应: {"success":true,"token":"sPVD9ewjuI...","user":{...}}
```

---

## 文件清单

```
pyWork/
├── plugins/auth/
│   ├── __init__.py(新建)
│   ├── plugin.py (新建, ~280行)
│   └── templates/
│       ├── login.html (新建, 2.1KB)
│       └── register.html (新建, 2.5KB)
├── static/css/
│   └── auth.css (新建, 4.8KB)
└── app/main.py
    (修改:添加 auth 路由、默认启用 auth 插件)
```

---

## 关键修复

### 问题 1: 插件加载失败

**原因**: AuthPlugin 未实现抽象方法 `init` 和 `routes`

**解决**: 添加 `init` 和 `routes` 方法实现

### 问题 2: enabled_plugins 不包含 auth

**原因**: 命令行参数 `--enabled` 默认值为 `"blog"`

**解决**:修改默认值为 `"blog,auth"`

### 问题 3: users 表缺少字段

**原因**: `put` 方法自动添加 `updated_at` 字段，users 表无此字段

**解决**: 使用直接 SQL 插入

### 问题 4: 密码验证失败

**原因**: 存储格式错误（`salt:$hash` vs `salt$hash`）

**解决**: 修复 f-string 格式

---

## Session 管理

当前使用内存字典存储 session：
```python
self.sessions: Dict[str, Dict] = {}
```

生产环境建议：
- 使用 Redis 存储
- 添加过期时间
- 添加 CSRF 保护
- 使用 HTTPS Only Cookie

---

## 访问地址

```
登录页面: http://localhost:8080/login
注册页面: http://localhost:8080/register
```

---

## 下一步

1. 添加用户个人主页
2. 添加密码找回功能
3. 实现社交登录（GitHub/Google OAuth）
4. 添加用户权限系统
5. 实现 Cookie Session（替代 Header Token）
6. 添加 CSRF 保护
