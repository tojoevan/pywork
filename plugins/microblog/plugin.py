"""Microblog plugin implementation"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, MCPResource, MCPPrompt, Route


class MicroblogPlugin(Plugin):
    """微博插件 - 快速分享"""

    MAX_LENGTH = 500
    # 匿名发布间隔：60秒
    ANONYMOUS_RATE_LIMIT = 60

    def __init__(self):
        super().__init__()
        # 频率控制：IP -> 最后发布时间（秒）
        self._ip_rate_limit: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "microblog"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.config = ctx.config
        self.ctx = ctx
        self._ctx = ctx  # 供基类鉴权方法使用
        self.template_engine = ctx.template_engine

    def routes(self) -> List[Route]:
        return [
            Route("/microblog", "GET", self.home, "microblog.home"),
            Route("/microblog", "POST", self.create_api, "microblog.create"),
            Route("/api/microblog", "GET", self.list_api, "microblog.list"),
            Route("/api/microblog/{post_id}", "GET", self.get_api, "microblog.get"),
            Route("/api/microblog/{post_id}", "PUT", self.update_api, "microblog.update"),
            Route("/api/microblog/{post_id}", "DELETE", self.delete_api, "microblog.delete"),
            Route("/api/microblog/{post_id}/approve", "POST", self.approve_post_api, "microblog.approve"),
            Route("/api/microblog/{post_id}/reject", "POST", self.reject_post_api, "microblog.reject"),
        ]

    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="create_microblog",
                description="发布一条微博动态",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "微博内容（500字以内）"},
                        "visibility": {"type": "string", "enum": ["public", "followers", "private"], "default": "public"}
                    },
                    "required": ["content"]
                },
                handler=self.create_post
            ),
            MCPTool(
                name="list_microblog",
                description="获取微博列表",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20}
                    }
                },
                handler=self.list_posts
            ),
            MCPTool(
                name="delete_microblog",
                description="删除微博",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"}
                    },
                    "required": ["id"]
                },
                handler=self.delete_post
            ),
        ]

    def mcp_prompts(self) -> List[MCPPrompt]:
        return [
            MCPPrompt(
                name="microblog-sharing-template",
                description="微博分享模板",
                template="帮我发一条微博：{{content}}\n\n字数控制在140字以内，适合快速分享。",
                arguments=[
                    {"name": "content", "description": "想分享的内容", "required": True}
                ]
            ),
        ]

    async def _get_author_id(self, request) -> int:
        """从请求中获取当前用户 ID"""
        user = await self.get_current_user(request)
        if user:
            return user["id"]
        return 1  # 默认匿名

    async def create_post(
        self,
        content: str,
        visibility: str = "public",
        mcp_token: str = None,
        author_id: int = 1,
        is_anonymous: bool = False
    ) -> Dict[str, Any]:
        if not content or not content.strip():
            return {"error": "内容不能为空"}
        if len(content) > self.MAX_LENGTH:
            return {"error": f"内容不能超过{self.MAX_LENGTH}字"}

        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        now = int(time.time())
        # 匿名用户 → 待审核状态
        if is_anonymous:
            post_status = "pending"
        else:
            post_status = visibility

        data = {
            "author_id": author_id,
            "content": content,
            "visibility": visibility,
            "status": post_status,
            "created_at": now,
            "updated_at": now,
        }
        record_id = await self.engine.put("microblog_posts", 0, data)
        if is_anonymous:
            return {"id": record_id, "created_at": now, "status": "pending", "message": "发布成功，待管理员审核通过后显示"}
        return {"id": record_id, "created_at": now}

    async def list_posts(self, limit: int = 20, offset: int = 0, mcp_token: str = None, include_pending: bool = False) -> List[Dict]:
        # 默认只显示已审核通过的微博，include_pending=True 时显示 pending 状态
        if include_pending:
            status_filter = "c.status IN ('public', 'pending')"
        else:
            status_filter = "c.status = 'public'"
        sql = f"""
            SELECT c.*, u.username as author_name, u.avatar as author_avatar
            FROM microblog_posts c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE {status_filter}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = await self.engine.fetchall(sql, (limit, offset))
        for row in rows:
            if not row.get("author_name"):
                row["author_name"] = "匿名"
        return rows

    async def delete_post(self, id: int, mcp_token: str = None) -> Dict:
        post = await self.engine.get("microblog_posts", id)
        if not post:
            return {"error": "微博不存在"}
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                if post.get("author_id") != user["id"] and user.get("role") != "admin":
                    return {"error": "无权删除"}
            else:
                return {"error": "无效的 Token"}
        await self.engine.delete("microblog_posts", id)
        return {"deleted": True}

    async def get_pending_posts(self) -> List[Dict]:
        """获取所有待审核微博（管理员用）"""
        sql = """
            SELECT c.*, u.username as author_name, u.avatar as author_avatar
            FROM microblog_posts c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE c.status = 'pending'
            ORDER BY c.created_at DESC
        """
        rows = await self.engine.fetchall(sql, ())
        for row in rows:
            if not row.get("author_name"):
                row["author_name"] = "匿名"
        return rows

    async def approve_post(self, post_id: int) -> Dict:
        """通过审核"""
        post = await self.engine.get("microblog_posts", post_id)
        if not post:
            return {"error": "微博不存在"}
        if post.get("status") == "public":
            return {"error": "已经是审核通过状态"}
        post["status"] = "public"
        post["updated_at"] = int(time.time())
        await self.engine.put("microblog_posts", post_id, post)
        return {"id": post_id, "status": "public"}

    async def reject_post(self, post_id: int) -> Dict:
        """拒绝审核，删除"""
        post = await self.engine.get("microblog_posts", post_id)
        if not post:
            return {"error": "微博不存在"}
        await self.engine.delete("microblog_posts", post_id)
        return {"id": post_id, "deleted": True}

    async def approve_post_api(self, post_id: int, request, **kwargs):
        """POST /api/microblog/{post_id}/approve"""
        user = await self.get_current_user(request)
        if not user or user.get("role") != "admin":
            return self.error_json("需要管理员权限", 403)
        return await self.approve_post(post_id)

    async def reject_post_api(self, post_id: int, request, **kwargs):
        """POST /api/microblog/{post_id}/reject"""
        user = await self.get_current_user(request)
        if not user or user.get("role") != "admin":
            return self.error_json("需要管理员权限", 403)
        return await self.reject_post(post_id)

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        if tool_name == "create_microblog":
            return await self.create_post(mcp_token=mcp_token, **arguments)
        elif tool_name == "list_microblog":
            return await self.list_posts(mcp_token=mcp_token, **arguments)
        elif tool_name == "delete_microblog":
            return await self.delete_post(mcp_token=mcp_token, **arguments)
        raise ValueError(f"Unknown tool: {tool_name}")

    # HTTP handlers
    async def home(self, request, **kwargs):
        """微博首页 - 渲染 HTML 页面"""
        from starlette.responses import HTMLResponse

        posts = await self.list_posts(limit=50)
        
        # 获取当前登录用户
        current_author_id = None
        user = await self.get_current_user(request)
        if user:
            current_author_id = user["id"]
        
        html = await self.template_engine.render(
            "microblog.html",
            {
                "posts": posts,
                "nav_page": "microblog",
                "current_author_id": current_author_id,
            }
        )
        return HTMLResponse(content=html)

    async def create_api(self, request, **kwargs):
        content = kwargs.get("content", "")
        if not content:
            try:
                body = await request.json()
                content = body.get("content", "")
            except:
                try:
                    form = await request.form()
                    content = form.get("content", "")
                except:
                    pass
        
        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"
        if "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        
        # 检测是否匿名
        current_user = await self.get_current_user(request)
        is_anonymous = not current_user
        
        # 匿名用户频率控制
        if is_anonymous:
            now = time.time()
            last_post = self._ip_rate_limit.get(client_ip, 0)
            if now - last_post < self.ANONYMOUS_RATE_LIMIT:
                remaining = int(self.ANONYMOUS_RATE_LIMIT - (now - last_post))
                return self.error_json(f"发布过于频繁，请 {remaining} 秒后再试", 429)
            # 更新发布时间
            self._ip_rate_limit[client_ip] = now
            # 清理过期的记录（防止内存泄漏）
            expired = now - 300  # 5分钟前的记录
            self._ip_rate_limit = {k: v for k, v in self._ip_rate_limit.items() if v > expired}
        
        author_id = await self._get_author_id(request)
        return await self.create_post(content=content, author_id=author_id, is_anonymous=is_anonymous)

    async def get_api(self, post_id: int, **kwargs):
        """获取单条微博"""
        post = await self.engine.get("microblog_posts", post_id)
        if not post:
            return self.error_json("微博不存在", 404)
        return post

    async def update_api(self, post_id: int, request, **kwargs):
        """更新微博"""
        # 鉴权
        user = await self.get_current_user(request)
        
        post = await self.engine.get("microblog_posts", post_id)
        if not post:
            return self.error_json("微博不存在", 404)
        
        if not user:
            return self.error_json("请先登录", 401)
        
        if post.get("author_id") != user["id"] and user.get("role") != "admin":
            return self.error_json("无权限修改他人的微博", 403)
        
        # 获取新内容
        content = kwargs.get("content")
        if not content:
            try:
                body = await request.json()
                content = body.get("content")
            except:
                pass
        
        if not content or not content.strip():
            return self.error_json("内容不能为空")
        
        if len(content) > self.MAX_LENGTH:
            return self.error_json(f"内容不能超过{self.MAX_LENGTH}字")
        
        # 更新
        post["content"] = content.strip()
        post["updated_at"] = int(time.time())
        await self.engine.put("microblog_posts", post_id, post)
        
        return {"id": post_id, "updated": True}

    async def delete_api(self, post_id: int, request, **kwargs):
        # 鉴权：只有作者或 admin 才能删除
        user = await self.get_current_user(request)
        
        post = await self.engine.get("microblog_posts", post_id)
        if not post:
            return self.error_json("微博不存在", 404)
        
        if not user:
            return self.error_json("请先登录", 401)
        
        if post.get("author_id") != user["id"] and user.get("role") != "admin":
            return self.error_json("无权限删除他人的微博", 403)
        
        await self.engine.delete("microblog_posts", post_id)
        return {"deleted": True}

    async def list_api(self, limit: int = 20, offset: int = 0, **kwargs):
        return await self.list_posts(limit=limit, offset=offset)
