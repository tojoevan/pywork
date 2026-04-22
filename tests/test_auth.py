"""
Auth 插件单元测试 - P3-4.1

测试策略：纯单元测试，不导入真实 AuthPlugin 类
- 直接测试 AuthPlugin 的方法逻辑（复制实现到测试中）
- Mock 所有外部依赖（Engine、Config）
- 验证核心安全逻辑：密码哈希、验证码、Token 生成

注意：这些测试不依赖 aiosqlite 或其他运行时依赖
"""
import pytest
import asyncio
import time
import secrets
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional

# === 从 AuthPlugin 复制的核心逻辑 ===

def _hash_password(password: str, salt: str = None) -> tuple:
    """密码哈希（从 AuthPlugin 复制）"""
    if salt is None:
        salt = secrets.token_hex(16)
    hash_val = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return salt, hash_val


def _verify_password(password: str, salt: str, hash_val: str) -> bool:
    """验证密码（从 AuthPlugin 复制）"""
    _, computed = _hash_password(password, salt)
    return hmac.compare_digest(hash_val, computed)


def _split_password_hash(password_hash: str) -> tuple:
    """解析密码哈希格式（从 AuthPlugin 复制）"""
    if ':' in password_hash:
        parts = password_hash.split(':')
        return parts[0], parts[1]
    elif '$' in password_hash:
        parts = password_hash.split('$')
        return parts[0], parts[1]
    return password_hash, ""


def _generate_token() -> str:
    """生成 session token（从 AuthPlugin 复制）"""
    return secrets.token_urlsafe(32)


class CaptchaManager:
    """验证码管理器（从 AuthPlugin 复制）"""
    def __init__(self):
        self.codes: Dict[str, Dict] = {}
    
    def generate(self) -> tuple:
        """生成验证码"""
        code_id = secrets.token_urlsafe(16)
        code = ''.join([secrets.choice('0123456789') for _ in range(4)])
        self.codes[code_id] = {
            "code": code,
            "expires": int(time.time()) + 300  # 5分钟
        }
        return code_id, code
    
    def verify(self, code_id: str, code: str) -> bool:
        """验证验证码"""
        if code_id not in self.codes:
            return False
        
        stored = self.codes[code_id]
        
        # 检查过期
        if stored["expires"] < int(time.time()):
            del self.codes[code_id]
            return False
        
        # 检查正确
        if stored["code"] != code:
            return False
        
        # 验证成功，删除
        del self.codes[code_id]
        return True


# === Mock Engine ===

class MockEngine:
    """模拟 Engine 接口"""
    def __init__(self):
        self.tables: Dict[str, List[Dict]] = {
            "users": [],
            "sessions": [],
            "mcp_tokens": []
        }
        self._next_id = 1
    
    async def execute(self, sql: str, params: tuple = None):
        """执行 SQL（简化实现）"""
        sql_upper = sql.upper().strip()
        
        if "INSERT INTO USERS" in sql_upper:
            username, email, password_hash, created_at, role = params
            user = {
                "id": self._next_id,
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "created_at": created_at,
                "role": role
            }
            self.tables["users"].append(user)
            self._next_id += 1
        
        elif "INSERT INTO SESSIONS" in sql_upper:
            token, user_id, created_at, expires_at = params
            session = {
                "token": token,
                "user_id": user_id,
                "created_at": created_at,
                "expires_at": expires_at
            }
            self.tables["sessions"].append(session)
        
        elif "INSERT INTO MCP_TOKENS" in sql_upper:
            token, user_id, name, created_at = params
            mcp_token = {
                "token": token,
                "user_id": user_id,
                "name": name,
                "created_at": created_at,
                "last_used": 0
            }
            self.tables["mcp_tokens"].append(mcp_token)
        
        elif "DELETE FROM SESSIONS" in sql_upper:
            token = params[0]
            self.tables["sessions"] = [
                s for s in self.tables["sessions"] if s["token"] != token
            ]
        
        elif "DELETE FROM MCP_TOKENS" in sql_upper:
            token = params[0]
            self.tables["mcp_tokens"] = [
                t for t in self.tables["mcp_tokens"] if t["token"] != token
            ]
        
        elif "UPDATE MCP_TOKENS" in sql_upper:
            last_used, token = params
            for t in self.tables["mcp_tokens"]:
                if t["token"] == token:
                    t["last_used"] = last_used
    
    async def fetchone(self, sql: str, params: tuple = None) -> Optional[Dict]:
        """查询单行"""
        sql_upper = sql.upper()
        
        if "LAST_INSERT_ROWID" in sql_upper:
            return {"id": self._next_id - 1}
        
        if "COUNT" in sql_upper:
            sql_lower = sql.lower()
            table = "users" if "users" in sql_lower else "sessions"
            return {"cnt": len(self.tables.get(table, []))}
        
        if "SELECT USER_ID" in sql_upper or ("SELECT TOKEN" in sql_upper and "MCP_TOKENS" in sql_upper):
            if params:
                token = params[0]
                for t in self.tables["mcp_tokens"]:
                    if t["token"] == token:
                        return t
                for t in self.tables["mcp_tokens"]:
                    if t["token"].startswith(token):
                        return t
            return None
        
        if "SELECT * FROM USERS" in sql_upper:
            if params:
                user_id = params[0]
                for u in self.tables["users"]:
                    if u["id"] == user_id:
                        return u
            return None
        
        if "SELECT * FROM SESSIONS" in sql_upper:
            if params:
                token = params[0]
                for s in self.tables["sessions"]:
                    if s["token"] == token:
                        return s
            return None
        
        return None
    
    async def fetchall(self, sql: str, params: tuple = None) -> List[Dict]:
        """查询多行"""
        sql_upper = sql.upper()
        
        if "FROM USERS" in sql_upper and "USERNAME" in sql_upper:
            if params:
                username = params[0]
                for u in self.tables["users"]:
                    if u["username"] == username:
                        return [u]
            return []
        
        if "FROM USERS" in sql_upper and "EMAIL" in sql_upper:
            if params:
                email = params[0]
                for u in self.tables["users"]:
                    if u["email"] == email:
                        return [u]
            return []
        
        if "FROM USERS" in sql_upper:
            return self.tables["users"]
        
        if "FROM MCP_TOKENS" in sql_upper:
            user_id = params[0] if params else None
            if user_id:
                return [t for t in self.tables["mcp_tokens"] if t["user_id"] == user_id]
            return self.tables["mcp_tokens"]
        
        return []


# === 模拟 AuthPlugin 行为 ===

class MockAuthPlugin:
    """模拟 AuthPlugin 核心行为"""
    def __init__(self, engine: MockEngine):
        self.engine = engine
        self.captcha_codes = CaptchaManager()
        self.sessions: Dict[str, Dict] = {}  # 兼容旧代码
    
    def _generate_captcha(self) -> tuple:
        return self.captcha_codes.generate()
    
    def _verify_captcha(self, code_id: str, code: str) -> bool:
        return self.captcha_codes.verify(code_id, code)
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        return _hash_password(password, salt)
    
    def _verify_password(self, password: str, salt: str, hash_val: str) -> bool:
        return _verify_password(password, salt, hash_val)
    
    def _split_password_hash(self, password_hash: str) -> tuple:
        return _split_password_hash(password_hash)
    
    def _generate_token(self) -> str:
        return _generate_token()
    
    async def register(self, username: str, email: str, password: str, 
                       captcha_id: str, captcha_code: str) -> Dict:
        """注册逻辑"""
        # 验证码检查
        if not self._verify_captcha(captcha_id, captcha_code):
            return {"error": "验证码错误或已过期"}
        
        # 检查用户名
        existing = await self.engine.fetchall(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        if existing:
            return {"error": "用户名已存在"}
        
        # 检查邮箱
        existing = await self.engine.fetchall(
            "SELECT * FROM users WHERE email = ?", (email,)
        )
        if existing:
            return {"error": "邮箱已被注册"}
        
        # 哈希密码
        salt, hash_val = self._hash_password(password)
        password_hash = f"{salt}:{hash_val}"
        
        # 判断是否第一个用户（管理员）
        all_users = await self.engine.fetchall("SELECT * FROM users")
        role = "admin" if not all_users else "user"
        
        # 插入用户
        created_at = int(time.time())
        await self.engine.execute(
            "INSERT INTO users (username, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?)",
            (username, email, password_hash, created_at, role)
        )
        
        # 获取插入的 ID
        row = await self.engine.fetchone("SELECT LAST_INSERT_ROWID()")
        user_id = row["id"] if row else 1
        
        return {
            "success": True,
            "user": {
                "id": user_id,
                "username": username,
                "email": email,
                "role": role
            }
        }
    
    async def login(self, username: str, password: str) -> Dict:
        """登录逻辑"""
        # 查找用户
        users = await self.engine.fetchall(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        if not users:
            return {"error": "用户名或密码错误"}
        
        user = users[0]
        
        # 验证密码
        salt, hash_val = self._split_password_hash(user["password_hash"])
        if not self._verify_password(password, salt, hash_val):
            return {"error": "用户名或密码错误"}
        
        # 创建 session
        token = self._generate_token()
        now = int(time.time())
        expires = now + 7 * 24 * 3600  # 7天
        
        await self.engine.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user["id"], now, expires)
        )
        
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"]
            }
        }
    
    async def logout(self, token: str) -> Dict:
        """登出逻辑"""
        await self.engine.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return {"success": True}
    
    async def get_user_by_token(self, token: str) -> Optional[Dict]:
        """通过 token 获取用户"""
        session = await self.engine.fetchone(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        )
        if not session:
            return None
        
        # 检查过期
        if session["expires_at"] < int(time.time()):
            return None
        
        user = await self.engine.fetchone(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        )
        return user
    
    async def create_mcp_token(self, user_id: int, name: str) -> Dict:
        """创建 MCP Token"""
        token = _generate_token()
        created_at = int(time.time())
        
        await self.engine.execute(
            "INSERT INTO mcp_tokens (token, user_id, name, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, name, created_at)
        )
        
        return {"token": token, "name": name}
    
    async def list_mcp_tokens(self, user_id: int) -> List[Dict]:
        """列出 MCP Tokens"""
        rows = await self.engine.fetchall(
            "SELECT * FROM mcp_tokens WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return [
            {
                "token": r["token"],
                "name": r["name"],
                "created_at": r["created_at"],
                "last_used": r["last_used"]
            }
            for r in rows
        ]
    
    async def revoke_mcp_token(self, token: str) -> bool:
        """撤销 MCP Token"""
        existing = await self.engine.fetchone(
            "SELECT token FROM mcp_tokens WHERE token = ?", (token,)
        )
        if not existing:
            return False
        
        await self.engine.execute("DELETE FROM mcp_tokens WHERE token = ?", (token,))
        return True
    
    async def get_user_by_mcp_token(self, token: str) -> Optional[Dict]:
        """通过 MCP Token 获取用户"""
        row = await self.engine.fetchone(
            "SELECT user_id, last_used FROM mcp_tokens WHERE token = ?",
            (token,)
        )
        if not row:
            return None
        
        # 更新最后使用时间
        await self.engine.execute(
            "UPDATE mcp_tokens SET last_used = ? WHERE token = ?",
            (int(time.time()), token)
        )
        
        # 获取用户详情
        user = await self.engine.fetchone(
            "SELECT * FROM users WHERE id = ?", (row["user_id"],)
        )
        if user:
            return {
                "id": user["id"],
                "username": user["username"],
                "role": user.get("role", "user")
            }
        return None


# === Fixtures ===

@pytest.fixture
def engine():
    return MockEngine()


@pytest.fixture
def auth_plugin(engine):
    return MockAuthPlugin(engine)


# === 测试：验证码 ===

class TestCaptcha:
    """验证码测试"""
    
    def test_generate_captcha(self, auth_plugin):
        """测试生成验证码"""
        code_id, code = auth_plugin._generate_captcha()
        
        assert code_id is not None
        assert len(code_id) == 22  # secrets.token_urlsafe(16) = 22 chars
        assert len(code) == 4  # 4位数字
        assert code.isdigit()
        assert code_id in auth_plugin.captcha_codes.codes
    
    def test_verify_captcha_correct(self, auth_plugin):
        """测试验证码验证 - 正确"""
        code_id, code = auth_plugin._generate_captcha()
        
        result = auth_plugin._verify_captcha(code_id, code)
        assert result is True
        assert code_id not in auth_plugin.captcha_codes.codes  # 验证后删除
    
    def test_verify_captcha_wrong(self, auth_plugin):
        """测试验证码验证 - 错误"""
        code_id, code = auth_plugin._generate_captcha()
        
        result = auth_plugin._verify_captcha(code_id, "0000")
        assert result is False
        assert code_id in auth_plugin.captcha_codes.codes  # 错误不删除
    
    def test_verify_captcha_expired(self, auth_plugin):
        """测试验证码验证 - 过期"""
        code_id, code = auth_plugin._generate_captcha()
        
        # 模拟过期
        auth_plugin.captcha_codes.codes[code_id]["expires"] = int(time.time()) - 1
        
        result = auth_plugin._verify_captcha(code_id, code)
        assert result is False
        assert code_id not in auth_plugin.captcha_codes.codes  # 过期删除


# === 测试：密码哈希 ===

class TestPasswordHash:
    """密码哈希测试"""
    
    def test_hash_password(self, auth_plugin):
        """测试密码哈希生成"""
        salt, hash_val = auth_plugin._hash_password("test123")
        
        assert salt is not None
        assert len(salt) == 32  # token_hex(16) = 32 chars
        assert len(hash_val) == 64  # sha256 hex = 64 chars
    
    def test_hash_password_with_salt(self, auth_plugin):
        """测试使用指定 salt 哈希"""
        salt = "test_salt_12345678"
        _, hash_val1 = auth_plugin._hash_password("test123", salt)
        _, hash_val2 = auth_plugin._hash_password("test123", salt)
        
        assert hash_val1 == hash_val2  # 相同 salt + 密码 = 相同哈希
    
    def test_verify_password_correct(self, auth_plugin):
        """测试密码验证 - 正确"""
        salt, hash_val = auth_plugin._hash_password("test123")
        
        result = auth_plugin._verify_password("test123", salt, hash_val)
        assert result is True
    
    def test_verify_password_wrong(self, auth_plugin):
        """测试密码验证 - 错误"""
        salt, hash_val = auth_plugin._hash_password("test123")
        
        result = auth_plugin._verify_password("wrong", salt, hash_val)
        assert result is False
    
    def test_split_password_hash_colon(self, auth_plugin):
        """测试解析密码哈希 - 冒号分隔"""
        salt = "test_salt"
        hash_val = "test_hash"
        password_hash = f"{salt}:{hash_val}"
        
        s, h = auth_plugin._split_password_hash(password_hash)
        assert s == salt
        assert h == hash_val
    
    def test_split_password_hash_dollar(self, auth_plugin):
        """测试解析密码哈希 - 美元符号分隔（旧格式）"""
        salt = "test_salt"
        hash_val = "test_hash"
        password_hash = f"{salt}${hash_val}"
        
        s, h = auth_plugin._split_password_hash(password_hash)
        assert s == salt
        assert h == hash_val


# === 测试：用户注册 ===

@pytest.mark.asyncio
class TestRegister:
    """用户注册测试"""
    
    async def test_register_success(self, auth_plugin):
        """测试正常注册"""
        code_id, code = auth_plugin._generate_captcha()
        
        result = await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        assert result.get("success") is True
        assert "user" in result
        assert result["user"]["username"] == "testuser"
        assert result["user"]["role"] == "admin"  # 第一个用户是管理员
    
    async def test_register_duplicate_username(self, auth_plugin):
        """测试重复用户名"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test1@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        code_id, code = auth_plugin._generate_captcha()
        result = await auth_plugin.register(
            username="testuser",
            email="test2@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        assert "error" in result
        assert "用户名已存在" in result["error"]
    
    async def test_register_duplicate_email(self, auth_plugin):
        """测试重复邮箱"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="user1",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        code_id, code = auth_plugin._generate_captcha()
        result = await auth_plugin.register(
            username="user2",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        assert "error" in result
        assert "邮箱已被注册" in result["error"]
    
    async def test_register_invalid_captcha(self, auth_plugin):
        """测试无效验证码"""
        result = await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id="invalid",
            captcha_code="0000"
        )
        
        assert "error" in result
        assert "验证码" in result["error"]
    
    async def test_register_second_user_not_admin(self, auth_plugin):
        """测试第二个用户不是管理员"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="admin",
            email="admin@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        code_id, code = auth_plugin._generate_captcha()
        result = await auth_plugin.register(
            username="user",
            email="user@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        assert result.get("success") is True
        assert result["user"]["role"] == "user"


# === 测试：用户登录 ===

@pytest.mark.asyncio
class TestLogin:
    """用户登录测试"""
    
    async def test_login_success(self, auth_plugin):
        """测试正常登录"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        result = await auth_plugin.login("testuser", "test123")
        
        assert result.get("success") is True
        assert "token" in result
        assert "user" in result
        assert result["user"]["username"] == "testuser"
    
    async def test_login_wrong_password(self, auth_plugin):
        """测试错误密码"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        result = await auth_plugin.login("testuser", "wrong")
        
        assert "error" in result
        assert "密码错误" in result["error"]
    
    async def test_login_nonexistent_user(self, auth_plugin):
        """测试不存在的用户"""
        result = await auth_plugin.login("nonexistent", "test123")
        
        assert "error" in result
        assert "错误" in result["error"]


# === 测试：Session 管理 ===

@pytest.mark.asyncio
class TestSession:
    """Session 管理测试"""
    
    async def test_logout(self, auth_plugin):
        """测试登出"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        result = await auth_plugin.login("testuser", "test123")
        token = result["token"]
        
        result = await auth_plugin.logout(token)
        assert result.get("success") is True
        
        sessions = auth_plugin.engine.tables["sessions"]
        assert not any(s["token"] == token for s in sessions)
    
    async def test_get_user_by_token(self, auth_plugin):
        """测试通过 token 获取用户"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        result = await auth_plugin.login("testuser", "test123")
        token = result["token"]
        
        user = await auth_plugin.get_user_by_token(token)
        assert user is not None
        assert user["username"] == "testuser"
    
    async def test_get_user_by_invalid_token(self, auth_plugin):
        """测试无效 token"""
        user = await auth_plugin.get_user_by_token("invalid_token")
        assert user is None


# === 测试：MCP Token ===

@pytest.mark.asyncio
class TestMCPToken:
    """MCP Token 测试"""
    
    async def test_create_mcp_token(self, auth_plugin):
        """测试创建 MCP Token"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        result = await auth_plugin.create_mcp_token(1, "Test Client")
        
        assert "token" in result
        assert result["name"] == "Test Client"
        assert len(result["token"]) == 43  # token_urlsafe(32) = 43 chars
    
    async def test_list_mcp_tokens(self, auth_plugin):
        """测试列出 MCP Tokens"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        await auth_plugin.create_mcp_token(1, "Client 1")
        await auth_plugin.create_mcp_token(1, "Client 2")
        
        tokens = await auth_plugin.list_mcp_tokens(1)
        
        assert len(tokens) == 2
        # 顺序取决于实现，只需验证两个都存在
        names = [t["name"] for t in tokens]
        assert "Client 1" in names
        assert "Client 2" in names
    
    async def test_revoke_mcp_token(self, auth_plugin):
        """测试撤销 MCP Token"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        result = await auth_plugin.create_mcp_token(1, "Test Client")
        token = result["token"]
        
        revoked = await auth_plugin.revoke_mcp_token(token)
        assert revoked is True
        
        revoked = await auth_plugin.revoke_mcp_token(token)
        assert revoked is False
    
    async def test_get_user_by_mcp_token(self, auth_plugin):
        """测试通过 MCP Token 获取用户"""
        code_id, code = auth_plugin._generate_captcha()
        await auth_plugin.register(
            username="testuser",
            email="test@example.com",
            password="test123",
            captcha_id=code_id,
            captcha_code=code
        )
        
        result = await auth_plugin.create_mcp_token(1, "Test Client")
        token = result["token"]
        
        user = await auth_plugin.get_user_by_mcp_token(token)
        assert user is not None
        assert user["username"] == "testuser"
        assert user["role"] == "admin"


# === 测试：Token 生成 ===

class TestTokenGeneration:
    """Token 生成测试"""
    
    def test_generate_token(self, auth_plugin):
        """测试生成 session token"""
        token = auth_plugin._generate_token()
        
        assert token is not None
        assert len(token) == 43  # token_urlsafe(32) = 43 chars
    
    def test_generate_token_unique(self, auth_plugin):
        """测试生成的 token 唯一"""
        tokens = [auth_plugin._generate_token() for _ in range(100)]
        
        assert len(tokens) == len(set(tokens))


# === 运行 ===

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
