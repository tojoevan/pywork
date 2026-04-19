"""
认证插件 - 用户登录/注册/管理
"""
import json
import time
import secrets
import hashlib
import urllib.parse
from typing import Optional, Dict, Any, List
from app.plugin import Plugin, PluginContext, MCPTool
from app.storage import Engine


class AuthPlugin(Plugin):
    """认证插件"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}  # 简单内存session，生产环境应使用Redis
        self.mcp_tokens: Dict[str, Dict] = {}  # MCP API tokens
        self.captcha_codes: Dict[str, Dict] = {}  # 验证码缓存: {code_id: {code, expires}}
        self.engine = None
        self.config = None

        # GitHub OAuth配置(从环境变量读取)
        self.github_client_id = None
        self.github_client_secret = None
        self.github_redirect_uri = None
    
    @property
    def name(self) -> str:
        return "auth"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    async def init(self, ctx):
        """Initialize auth plugin"""
        self.engine = ctx.engine
        self.config = ctx.config
        
        # 加载 OAuth 配置
        import os
        self.github_client_id = os.environ.get("GITHUB_CLIENT_ID")
        self.github_client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
        self.github_redirect_uri = os.environ.get("GITHUB_REDIRECT_URI", "http://localhost:8080/auth/github/callback")
        
        # 初始化 sessions 表
        await self._init_sessions_table()
    
    async def _init_sessions_table(self):
        """创建 sessions 表"""
        await self.engine.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        # 清理过期 session
        import time
        await self.engine.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
    
    def routes(self):
        """HTTP routes"""
        return []  # 路由在 main.py 中注册
    
    def _generate_captcha(self) -> tuple:
        """生成验证码，返回 (code_id, code_text)"""
        code_id = secrets.token_urlsafe(16)
        # 生成4位数字验证码
        code = ''.join([str(secrets.randbelow(10)) for _ in range(4)])
        expires = int(time.time()) + 300  # 5分钟有效期
        self.captcha_codes[code_id] = {
            "code": code,
            "expires": expires
        }
        return code_id, code
    
    def _verify_captcha(self, code_id: str, code: str) -> bool:
        """验证验证码"""
        if not code_id or not code:
            return False
        data = self.captcha_codes.get(code_id)
        if not data:
            return False
        # 检查是否过期
        if int(time.time()) > data["expires"]:
            del self.captcha_codes[code_id]
            return False
        # 验证代码（不区分大小写）
        if data["code"].lower() == code.lower():
            # 验证成功后删除，防止重复使用
            del self.captcha_codes[code_id]
            return True
        return False
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """密码加密"""
        if not salt:
            salt = secrets.token_hex(16)
        hash_val = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return salt, hash_val.hex()
    
    def _verify_password(self, password: str, salt: str, hash_val: str) -> bool:
        """密码验证"""
        _, new_hash = self._hash_password(password, salt)
        return secrets.compare_digest(new_hash, hash_val)
    
    def _split_password_hash(self, password_hash: str) -> tuple:
        """解析密码哈希字符串，返回 (salt, hash)
        支持格式: salt:hash (新格式) 和 salt$hash (旧格式)
        """
        if ':' in password_hash:
            parts = password_hash.split(':', 1)
        elif '$' in password_hash:
            parts = password_hash.split('$', 1)
        else:
            return None, password_hash
        salt = parts[0]
        hash_val = parts[1] if len(parts) > 1 else ''
        # 兼容旧格式：去掉 hash 值的前导 '$'
        if hash_val.startswith('$'):
            hash_val = hash_val[1:]
        return salt, hash_val
    
    def _generate_token(self) -> str:
        """生成session token"""
        return secrets.token_urlsafe(32)
    
    # === 核心功能 ===
    
    async def register(self, username: str, email: str, password: str, captcha_id: str = None, captcha_code: str = None) -> Dict:
        """用户注册"""
        # 验证验证码
        if not captcha_id or not captcha_code:
            return {"error": "请输入验证码"}
        if not self._verify_captcha(captcha_id, captcha_code):
            return {"error": "验证码错误或已过期"}
        
        # 检查用户名是否存在
        existing = await self.engine.query("users", username=username)
        if existing:
            return {"error": "用户名已存在"}
        
        # 检查邮箱是否存在
        if email:
            existing = await self.engine.query("users", email=email)
            if existing:
                return {"error": "邮箱已被注册"}
        
        # 创建用户
        salt, password_hash = self._hash_password(password)
        created_at = int(time.time())
        
        # 第一个注册的用户自动成为管理员
        row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM users")
        is_first = row["cnt"] == 0 if row else True
        role = "admin" if is_first else "user"
        
        # 直接使用 SQL 插入
        await self.engine.execute(
            "INSERT INTO users (username, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?)",
            (username, email, f"{salt}:{password_hash}", created_at, role)
        )
        
        # 获取新创建的ID
        row = await self.engine.fetchone("SELECT last_insert_rowid() as id")
        user_id = row["id"] if row else None
        
        user = {
            "id": user_id,
            "username": username,
            "email": email,
            "created_at": created_at,
            "role": "user"
        }
        
        return {"success": True, "user": user}
    
    async def login(self, username: str, password: str) -> Dict:
        """用户登录"""
        # 查找用户
        users = await self.engine.query("users", username=username)
        if not users:
            return {"error": "用户名或密码错误"}
        
        user = users[0]
        
        # 验证密码
        try:
            salt, hash_val = self._split_password_hash(user["password_hash"])
            if not salt:
                return {"error": "用户数据异常"}
        except:
            return {"error": "用户数据异常"}
        
        if not self._verify_password(password, salt, hash_val):
            return {"error": "用户名或密码错误"}
        
        # 生成session
        token = self._generate_token()
        import time
        expires_at = int(time.time()) + 7 * 24 * 3600  # 7天过期
        
        # 写入数据库
        await self.engine.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user["id"], int(time.time()), expires_at)
        )
        
        # 同时保留内存缓存（可选，用于快速访问）
        self.sessions[token] = {
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": int(time.time())
        }
        
        del user["password_hash"]
        return {"success": True, "token": token, "user": user}
    
    async def logout(self, token: str) -> Dict:
        """用户登出"""
        # 从数据库删除
        await self.engine.execute("DELETE FROM sessions WHERE token = ?", (token,))
        # 从内存删除
        if token in self.sessions:
            del self.sessions[token]
        return {"success": True}
    
    # === GitHub OAuth ===
    
    def get_github_auth_url(self, state: str = None) -> str:
        """生成 GitHub 授权 URL"""
        if not self.github_client_id:
            return None
        
        if not state:
            state = secrets.token_urlsafe(16)
        
        params = {
            "client_id": self.github_client_id,
            "redirect_uri": self.github_redirect_uri,
            "scope": "read:user user:email",
            "state": state
        }
        
        return f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    async def github_callback(self, code: str, state: str = None) -> Dict:
        """处理 GitHub OAuth 回调"""
        if not self.github_client_id or not self.github_client_secret:
            return {"error": "GitHub OAuth 未配置"}
        
        try:
            # 用 code 换取 access_token
            token_data = await self._exchange_github_code(code)
            if "error" in token_data:
                return token_data
            
            access_token = token_data.get("access_token")
            if not access_token:
                return {"error": "获取 access_token 失败"}
            
            # 获取 GitHub 用户信息
            github_user = await self._get_github_user(access_token)
            if "error" in github_user:
                return github_user
            
            # 查找或创建用户
            user = await self._find_or_create_github_user(github_user)
            if "error" in user:
                return user
            
            # 生成 session
            token = self._generate_token()
            import time
            expires_at = int(time.time()) + 7 * 24 * 3600  # 7天过期
            
            # 写入数据库
            await self.engine.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user["id"], int(time.time()), expires_at)
            )
            
            # 同时保留内存缓存
            self.sessions[token] = {
                "user_id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "github_id": github_user.get("id"),
                "created_at": int(time.time())
            }
            
            return {"success": True, "token": token, "user": user}
            
        except Exception as e:
            return {"error": f"OAuth 错误: {str(e)}"}
    
    async def _exchange_github_code(self, code: str) -> Dict:
        """用 code 换取 access_token"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.github_client_id,
                    "client_secret": self.github_client_secret,
                    "code": code,
                    "redirect_uri": self.github_redirect_uri
                }
            ) as resp:
                data = await resp.json()
                
                if "error" in data:
                    return {"error": data.get("error_description", data["error"])}
                
                return data
    
    async def _get_github_user(self, access_token: str) -> Dict:
        """获取 GitHub 用户信息"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            # 获取用户基本信息
            async with session.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
            ) as resp:
                user_data = await resp.json()
                
                if "message" in user_data:
                    return {"error": user_data["message"]}
                
                # 如果用户没有公开邮箱，尝试获取私有邮箱
                if not user_data.get("email"):
                    async with session.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/json"
                        }
                    ) as email_resp:
                        emails = await email_resp.json()
                        if isinstance(emails, list):
                            # 优先使用主邮箱
                            for email in emails:
                                if email.get("primary"):
                                    user_data["email"] = email.get("email")
                                    break
                
                return user_data
    
    async def _find_or_create_github_user(self, github_user: Dict) -> Dict:
        """查找或创建 GitHub 用户"""
        github_id = str(github_user.get("id"))
        github_login = github_user.get("login")
        github_email = github_user.get("email")
        github_avatar = github_user.get("avatar_url")
        
        # 先尝试通过 github_id 查找用户
        # 需要检查 users 表是否有 github_id 字段
        try:
            users = await self.engine.query("users", github_id=github_id)
            if users:
                user = users[0]
                if "password_hash" in user:
                    del user["password_hash"]
                return user
        except:
            pass# 字段可能不存在，继续创建
        
        # 尝试通过邮箱查找
        if github_email:
            users = await self.engine.query("users", email=github_email)
            if users:
                user = users[0]
                # 更新 github_id
                try:
                    await self.engine.execute(
                        "UPDATE users SET github_id = ? WHERE id = ?",
                        (github_id, user["id"])
                    )
                except:
                    pass
                if "password_hash" in user:
                    del user["password_hash"]
                return user
        
        # 创建新用户
        username = github_login
        # 检查用户名是否已存在
        existing = await self.engine.query("users", username=username)
        if existing:
            username = f"{github_login}_{github_id}"
        
        created_at = int(time.time())
        
        # 第一个注册的用户自动成为管理员
        row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM users")
        is_first = row["cnt"] == 0 if row else True
        role = "admin" if is_first else "user"
        
        try:
            # 尝试插入包含 github_id 的记录
            await self.engine.execute(
                "INSERT INTO users (username, email, created_at, role, avatar, github_id) VALUES (?, ?, ?, ?, ?, ?)",
                (username, github_email, created_at, role, github_avatar, github_id)
            )
        except:
            # 如果 github_id 字段不存在，使用基本字段
            await self.engine.execute(
                "INSERT INTO users (username, email, created_at, role, avatar) VALUES (?, ?, ?, ?, ?)",
                (username, github_email, created_at, role, github_avatar)
            )
        
        # 获取新用户
        row = await self.engine.fetchone("SELECT last_insert_rowid() as id")
        user_id = row["id"] if row else None
        
        user = {
            "id": user_id,
            "username": username,
            "email": github_email,
            "created_at": created_at,
            "role": "user",
            "avatar": github_avatar
        }
        
        return user
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """获取用户信息"""
        user = await self.engine.get("users", user_id)
        if user and "password_hash" in user:
            del user["password_hash"]
        return user
    
    async def get_user_by_token(self, token: str) -> Optional[Dict]:
        """通过token获取用户（从数据库读取）"""
        import time
        # 从数据库查询 session
        session = await self.engine.fetchone(
            "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)
        )
        if not session:
            return None
        
        # 检查是否过期
        if session[1] < int(time.time()):
            # 过期则删除
            await self.engine.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        
        user = await self.get_user(session[0])
        if user:
            user["token"] = token
        return user
    
    async def update_user(self, user_id: int, **kwargs) -> Dict:
        """更新用户信息"""
        # 不允许直接修改密码
        if "password_hash" in kwargs:
            del kwargs["password_hash"]
        
        kwargs["id"] = user_id
        return await self.engine.update("users", kwargs)
    
    async def change_password(self, user_id: int, old_password: str, new_password: str) -> Dict:
        """修改密码"""
        user = await self.engine.get("users", user_id)
        if not user:
            return {"error": "用户不存在"}
        
        # 验证旧密码
        try:
            salt, hash_val = user["password_hash"].split("$")
        except:
            return {"error": "用户数据异常"}
        
        if not self._verify_password(old_password, salt, hash_val):
            return {"error": "原密码错误"}
        
        # 设置新密码
        new_salt, new_hash = self._hash_password(new_password)
        await self.engine.update("users", {
            "id": user_id,
            "password_hash": f"{new_salt}:${new_hash}"
        })
        
        return {"success": True}
    
    async def list_users(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        """列出用户"""
        users = await self.engine.list("users", limit=limit, offset=offset)
        for user in users:
            if "password_hash" in user:
                del user["password_hash"]
        return users
    
    # === MCP工具 ===
    
    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="auth_register",
                description="用户注册",
                input_schema={
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "description": "用户名"},
                        "email": {"type": "string", "description": "邮箱"},
                        "password": {"type": "string", "description": "密码"}
                    },
                    "required": ["username", "password"]
                }
            ),
            MCPTool(
                name="auth_login",
                description="用户登录",
                input_schema={
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "description": "用户名"},
                        "password": {"type": "string", "description": "密码"}
                    },
                    "required": ["username", "password"]
                }
            ),
            MCPTool(
                name="auth_logout",
                description="用户登出",
                input_schema={
                    "type": "object",
                    "properties": {
                        "token": {"type": "string", "description": "Session token"}
                    },
                    "required": ["token"]
                }
            ),
            MCPTool(
                name="auth_get_user",
                description="获取用户信息",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer", "description": "用户ID"}
                    },
                    "required": ["user_id"]
                }
            ),
            MCPTool(
                name="auth_github_url",
                description="获取 GitHub OAuth 授权链接",
                input_schema={
                    "type": "object",
                    "properties": {
                        "state": {"type": "string", "description": "CSRF state 参数"}
                    }
                }
            ),
            MCPTool(
                name="auth_create_mcp_token",
                description="创建新的 MCP API Token（需要认证）",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Token 名称"}
                    }
                }
            ),
            MCPTool(
                name="auth_list_mcp_tokens",
                description="列出所有 MCP Tokens（需要认证）",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
        ]
    
    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        # MCP Token 认证
        user = None
        if mcp_token:
            user = await self.get_user_by_mcp_token(mcp_token)

        if tool_name == "auth_register":
            return await self.register(**arguments)
        elif tool_name == "auth_login":
            return await self.login(**arguments)
        elif tool_name == "auth_logout":
            return await self.logout(**arguments)
        elif tool_name == "auth_get_user":
            return await self.get_user(**arguments)
        elif tool_name == "auth_create_mcp_token":
            if not user:
                return {"error": "需要有效的 MCP Token"}
            return await self.create_mcp_token(user["id"], arguments.get("name", "New Token"))
        elif tool_name == "auth_list_mcp_tokens":
            if not user:
                return {"error": "需要有效的 MCP Token"}
            return await self.list_mcp_tokens(user["id"])
        elif tool_name == "auth_revoke_mcp_token":
            if not user:
                return {"error": "需要有效的 MCP Token"}
            # 这里需要完整的 token，但列表返回的是脱敏版本
            # 实际撤销需要通过 API 进行
            return {"error": "请通过 Web 界面撤销 Token"}
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    def mcp_resources(self) -> List[Dict]:
        return [
            {
                "uri": "auth://users",
                "name": "用户列表",
                "description": "所有注册用户",
                "mimeType": "application/json"
            }
        ]
    
    async def mcp_read(self, uri: str) -> str:
        if uri == "auth://users":
            users = await self.list_users()
            return json.dumps(users, ensure_ascii=False, indent=2)
        raise ValueError(f"Unknown resource: {uri}")
    
    # === API路由 ===
    
    async def _get_request_data(self, request):
        """获取请求数据，支持 JSON 和表单"""
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            return await request.json()
        else:
            # 表单提交
            form = await request.form()
            return dict(form)
    
    async def register_api(self, request):
        """注册API"""
        data = await self._get_request_data(request)
        result = await self.register(
            username=data.get("username"),
            email=data.get("email"),
            password=data.get("password"),
            captcha_id=data.get("captcha_id"),
            captcha_code=data.get("captcha_code")
        )
        # 表单提交返回 HTML 响应
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            from starlette.responses import HTMLResponse
            if result.get("success"):
                return HTMLResponse(content="""
                    <!DOCTYPE html>
                    <html><head><meta charset="utf-8"><title>注册成功</title></head>
                    <body style="font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5">
                        <div style="text-align:center;background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)">
                            <h1 style="color:#2d2d2d;margin-bottom:16px">注册成功！</h1>
                            <p style="color:#666;margin-bottom:24px">账号已创建，现在可以登录了</p>
                            <a href="/login" style="display:inline-block;background:#2d2d2d;color:white;padding:12px 24px;text-decoration:none;border-radius:4px">立即登录</a>
                        </div>
                    </body></html>
                """)
            else:
                error_msg = result.get("error", "注册失败")
                return HTMLResponse(content=f"""
                    <!DOCTYPE html>
                    <html><head><meta charset="utf-8"><title>注册失败</title></head>
                    <body style="font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5">
                        <div style="text-align:center;background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)">
                            <h1 style="color:#e74c3c;margin-bottom:16px">注册失败</h1>
                            <p style="color:#666;margin-bottom:24px">{error_msg}</p>
                            <a href="/register" style="display:inline-block;background:#2d2d2d;color:white;padding:12px 24px;text-decoration:none;border-radius:4px">重新注册</a>
                        </div>
                    </body></html>
                """)
        return result
    
    async def login_api(self, request):
        """登录API"""
        data = await self._get_request_data(request)
        result = await self.login(
            username=data.get("username"),
            password=data.get("password")
        )
        # 表单提交返回 HTML 响应并设置 Cookie
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            from starlette.responses import HTMLResponse
            if result.get("success"):
                token = result.get("token")
                response = HTMLResponse(content="""
                    <!DOCTYPE html>
                    <html><head><meta charset="utf-8"><title>登录成功</title>
                    <script>setTimeout(function(){window.location.href='/';},800);</script>
                    </head>
                    <body style="font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5">
                        <div style="text-align:center;background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)">
                            <h1 style="color:#10b981;margin-bottom:16px">登录成功！</h1>
                            <p style="color:#666;margin-bottom:8px">欢迎回来，正在跳转...</p>
                            <p style="color:#999;font-size:13px">如果没有自动跳转，<a href="/" style="color:#10b981">点击这里</a></p>
                        </div>
                    </body></html>
                """)
                response.set_cookie(
                    key="auth_token",
                    value=token,
                    httponly=True,
                    max_age=7 * 24 * 3600
                )
                return response
            else:
                error_msg = result.get("error", "登录失败")
                return HTMLResponse(content=f"""
                    <!DOCTYPE html>
                    <html><head><meta charset="utf-8"><title>登录失败</title></head>
                    <body style="font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f5f5f5">
                        <div style="text-align:center;background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)">
                            <h1 style="color:#e74c3c;margin-bottom:16px">登录失败</h1>
                            <p style="color:#666;margin-bottom:24px">{error_msg}</p>
                            <a href="/login" style="display:inline-block;background:#2d2d2d;color:white;padding:12px 24px;text-decoration:none;border-radius:4px">重新登录</a>
                        </div>
                    </body></html>
                """)
        return result
    
    async def logout_api(self, request):
        """登出API - 优先从 Cookie 读取 token"""
        token = request.cookies.get("auth_token", "")
        if not token:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
        result = await self.logout(token)
        # 返回响应并清除 Cookie
        from starlette.responses import JSONResponse
        response = JSONResponse(content=result)
        response.delete_cookie("auth_token")
        return response
    
    async def me_api(self, request):
        """当前用户API - 优先从 Cookie 读取 token，兼容 Authorization header"""
        # 优先从 Cookie 读取
        token = request.cookies.get("auth_token", "")
        # 兼容 Authorization header
        if not token:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user = await self.get_user_by_token(token)
        if user:
            return user
        return {"error": "未登录"}

    async def captcha_api(self):
        """生成验证码图片API"""
        import base64
        from io import BytesIO

        code_id, code = self._generate_captcha()

        # 生成简单的验证码图片 (PIL)
        try:
            from PIL import Image, ImageDraw, ImageFont

            # 创建图片
            img = Image.new('RGB', (100, 40), color='#f3f4f6')
            draw = ImageDraw.Draw(img)

            # 添加干扰线
            import random
            for _ in range(3):
                x1, y1 = random.randint(0, 100), random.randint(0, 40)
                x2, y2 = random.randint(0, 100), random.randint(0, 40)
                draw.line([(x1, y1), (x2, y2)], fill='#d1d5db', width=1)

            # 添加干扰点
            for _ in range(30):
                x, y = random.randint(0, 100), random.randint(0, 40)
                draw.point((x, y), fill='#9ca3af')

            # 绘制文字
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            except:
                font = ImageFont.load_default()

            # 居中绘制验证码
            text = code
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (100 - text_width) // 2
            y = (40 - text_height) // 2 - 5

            # 绘制文字（带轻微阴影）
            draw.text((x+1, y+1), text, font=font, fill='#9ca3af')
            draw.text((x, y), text, font=font, fill='#374151')

            # 转换为 base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return {
                "id": code_id,
                "image": f"data:image/png;base64,{img_base64}"
            }
        except ImportError:
            # PIL 未安装，返回纯文本验证码（仅用于开发测试）
            return {
                "id": code_id,
                "code": code,  # 仅用于测试，生产环境应使用图片
                "image": ""
            }

    async def github_auth_url_api(self, request):
        """获取 GitHub OAuth 授权链接"""
        url = self.get_github_auth_url()
        if not url:
            return {"error": "GitHub OAuth 未配置"}
        return {"url": url}
    
    async def github_callback_api(self, request):
        """GitHub OAuth 回调"""
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code:
            return {"error": "缺少 code 参数"}

        return await self.github_callback(code, state)

    # === MCP Token 管理 ===

    async def create_mcp_token(self, user_id: int, name: str = "MCP Client") -> Dict:
        """创建 MCP API Token"""
        token = secrets.token_urlsafe(32)
        created_at = int(time.time())

        self.mcp_tokens[token] = {
            "user_id": user_id,
            "name": name,
            "created_at": created_at,
            "last_used": None
        }

        return {
            "token": token,
            "name": name,
            "created_at": created_at
        }

    async def revoke_mcp_token(self, token: str) -> bool:
        """撤销 MCP Token"""
        if token in self.mcp_tokens:
            del self.mcp_tokens[token]
            return True
        return False

    async def list_mcp_tokens(self, user_id: int) -> List[Dict]:
        """列出用户的 MCP Tokens"""
        tokens = []
        for token, info in self.mcp_tokens.items():
            if info["user_id"] == user_id:
                tokens.append({
                    "id": token[:16],  # 用于前端识别和删除
                    "prefix": token[:8],  # 显示前8位
                    "name": info["name"],
                    "created_at": info["created_at"],
                    "last_used": info["last_used"]
                })
        return tokens

    async def get_user_by_mcp_token(self, token: str) -> Optional[Dict]:
        """通过 MCP Token 获取用户"""
        if token not in self.mcp_tokens:
            return None

        info = self.mcp_tokens[token]
        # 更新最后使用时间
        info["last_used"] = int(time.time())

        # 获取用户详情
        user = await self.get_user(info["user_id"])
        if user:
            return {
                "id": user["id"],
                "username": user["username"],
                "role": user.get("role", "user"),
                "token_name": info["name"]
            }
        return None
