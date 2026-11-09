"""微博单条可见性 —— 真 SQLite 集成测试.

背景（P0）：待审（status=pending）微博曾被匿名用户通过
``/microblog/{id}`` 与 ``/api/microblog/{id}`` 直接按 ID 读到，
因为两个 handler 都只执行 ``WHERE c.id = ?``，没有状态/权限判定。

这里用内存 SQLite 跑真实 SQL，并让 ``get_current_user`` 走真实的
cookie / Authorization Bearer 解析 + auth 插件查用户，避免用 monkeypatch
把「拿不到登录态」这一层绕过去。
"""
import json
import sqlite3

import pytest
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from plugins.microblog.plugin import MicroblogPlugin


class AsyncSQLiteEngine:
    """最小 engine 适配器：只实现 detail / get_api 用到的 fetchone。"""

    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE microblog_posts ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "  author_id INTEGER NOT NULL DEFAULT 0, "
            "  content TEXT DEFAULT '', "
            "  visibility TEXT DEFAULT 'public', "
            "  status TEXT DEFAULT 'public', "
            "  created_at INTEGER DEFAULT 0, "
            "  updated_at INTEGER DEFAULT 0)"
        )
        self.con.execute(
            "CREATE TABLE users ("
            "  id INTEGER PRIMARY KEY, username TEXT DEFAULT '', "
            "  nickname TEXT DEFAULT '', display_name TEXT DEFAULT '', "
            "  avatar TEXT DEFAULT '', role TEXT DEFAULT 'user')"
        )

    async def fetchone(self, sql, params=()):
        row = self.con.execute(sql, params).fetchone()
        return dict(row) if row else None

    def add_user(self, uid, name, role="user"):
        self.con.execute(
            "INSERT INTO users (id, username, nickname, role) VALUES (?, ?, ?, ?)",
            (uid, name, name, role),
        )

    def add_post(self, pid, author_id, status="public", content="hello"):
        self.con.execute(
            "INSERT INTO microblog_posts "
            "(id, author_id, content, visibility, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'public', ?, 0, 0)",
            (pid, author_id, content, status),
        )

    def close(self):
        self.con.close()


class AuthStub:
    """替代 auth 插件：按 token 返回用户。"""

    def __init__(self, users_by_token):
        self.users_by_token = users_by_token

    async def get_user_by_token(self, token):
        return self.users_by_token.get(token)


class CtxStub:
    def __init__(self, auth):
        self.auth = auth

    def get_plugin(self, name):
        return self.auth if name == "auth" else None


class TemplateStub:
    def __init__(self):
        self.rendered = []

    async def render(self, name, context):
        self.rendered.append((name, context))
        return "<html>ok</html>"


def make_request(token=None, bearer=None):
    """构造真实 starlette Request（cookie / Authorization 两种登录态）。"""
    headers = []
    if token:
        headers.append((b"cookie", f"auth_token={token}".encode()))
    if bearer:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/microblog/2",
        "raw_path": b"/microblog/2",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def http_status(result):
    """dict 返回值表示成功响应（无 status_code），否则取响应状态码。"""
    return getattr(result, "status_code", 200)


@pytest.fixture
def rig():
    engine = AsyncSQLiteEngine()
    engine.add_user(1, "alice")
    engine.add_user(2, "bob")
    engine.add_user(99, "admin", role="admin")
    engine.add_post(1, author_id=1, status="public")
    engine.add_post(2, author_id=1, status="pending", content="待审内容")
    engine.add_post(3, author_id=0, status="pending", content="匿名投稿")

    plugin = MicroblogPlugin()
    plugin.engine = engine
    plugin._ctx = CtxStub(AuthStub({
        "alice-token": {"id": 1, "role": "user"},
        "bob-token": {"id": 2, "role": "user"},
        "admin-token": {"id": 99, "role": "admin"},
    }))
    plugin.template_engine = TemplateStub()
    yield plugin, engine
    engine.close()


@pytest.mark.asyncio
async def test_anonymous_cannot_read_pending_detail(rig):
    plugin, _ = rig
    resp = await plugin.detail(make_request(), 2)
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 404
    assert plugin.template_engine.rendered == []  # 未渲染即不泄露内容


@pytest.mark.asyncio
async def test_anonymous_cannot_read_pending_api(rig):
    plugin, _ = rig
    # 路由层传进来的是字符串 post_id，这里模拟真实调用
    resp = await plugin.get_api("2", request=make_request())
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert json.loads(resp.body)["error"] == "微博不存在"


@pytest.mark.asyncio
async def test_anonymous_cannot_read_pending_anonymous_submission(rig):
    plugin, _ = rig
    assert http_status(await plugin.detail(make_request(), 3)) == 404
    assert http_status(await plugin.get_api(3, request=make_request())) == 404


@pytest.mark.asyncio
async def test_admin_can_read_pending_via_cookie(rig):
    plugin, _ = rig
    req = make_request(token="admin-token")
    detail_resp = await plugin.detail(req, 3)
    assert http_status(detail_resp) == 200
    assert plugin.template_engine.rendered[0][1]["post"]["content"] == "匿名投稿"
    assert plugin.template_engine.rendered[0][1]["is_admin"] is True

    api_resp = await plugin.get_api(3, request=req)
    assert isinstance(api_resp, dict)
    assert api_resp["content"] == "匿名投稿"
    assert api_resp["author_name"] == "匿名"


@pytest.mark.asyncio
async def test_admin_can_read_pending_via_bearer_header(rig):
    plugin, _ = rig
    req = make_request(bearer="admin-token")
    assert http_status(await plugin.detail(req, 2)) == 200
    assert isinstance(await plugin.get_api(2, request=req), dict)


@pytest.mark.asyncio
async def test_author_can_read_own_pending(rig):
    plugin, _ = rig
    req = make_request(token="alice-token")
    assert http_status(await plugin.detail(req, 2)) == 200
    assert isinstance(await plugin.get_api(2, request=req), dict)


@pytest.mark.asyncio
async def test_other_logged_in_user_cannot_read_pending(rig):
    plugin, _ = rig
    req = make_request(token="bob-token")
    assert http_status(await plugin.detail(req, 2)) == 404
    assert http_status(await plugin.get_api(2, request=req)) == 404


@pytest.mark.asyncio
async def test_invalid_token_is_treated_as_anonymous(rig):
    plugin, _ = rig
    req = make_request(token="expired-token")
    assert http_status(await plugin.detail(req, 2)) == 404
    assert http_status(await plugin.get_api(2, request=req)) == 404


@pytest.mark.asyncio
async def test_public_post_still_readable_anonymously(rig):
    plugin, _ = rig
    req = make_request()
    detail_resp = await plugin.detail(req, 1)
    assert http_status(detail_resp) == 200
    assert plugin.template_engine.rendered[0][1]["post"]["content"] == "hello"

    api_resp = await plugin.get_api(1, request=req)
    assert isinstance(api_resp, dict)
    assert api_resp["author_name"] == "alice"


@pytest.mark.asyncio
async def test_missing_post_returns_404_everywhere(rig):
    plugin, _ = rig
    req = make_request(token="admin-token")
    assert http_status(await plugin.detail(req, 999)) == 404
    assert http_status(await plugin.get_api(999, request=req)) == 404


@pytest.mark.asyncio
async def test_no_request_defaults_to_deny(rig):
    """内部调用拿不到 request 时按匿名处理，不能意外放行。"""
    plugin, _ = rig
    assert http_status(await plugin.get_api(2)) == 404
    assert isinstance(await plugin.get_api(1), dict)  # public 不受影响
