"""Microblog plugin implementation"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, MCPResource, MCPPrompt, Route


class MicroblogPlugin(Plugin):
    """微博插件 - 快速分享"""

    MAX_LENGTH = 500

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
        self.template_engine = ctx.template_engine

    def _auth(self):
        if self.ctx:
            return self.ctx.get_plugin("auth")
        return None

    def routes(self) -> List[Route]:
        return [
            Route("/microblog", "GET", self.home, "microblog.home"),
            Route("/microblog", "POST", self.create_api, "microblog.create"),
            Route("/api/microblog", "GET", self.list_api, "microblog.list"),
            Route("/api/microblog/{post_id}", "DELETE", self.delete_api, "microblog.delete"),
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
        token = request.cookies.get("auth_token", "")
        if not token:
            auth = self._auth()
            if auth:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token:
            auth = self._auth()
            if auth:
                user = await auth.get_user_by_token(token)
                if user:
                    return user["id"]
        return 1  # 默认匿名

    async def create_post(
        self,
        content: str,
        visibility: str = "public",
        mcp_token: str = None,
        author_id: int = 1
    ) -> Dict[str, Any]:
        if not content or not content.strip():
            return {"error": "内容不能为空"}
        if len(content) > self.MAX_LENGTH:
            return {"error": f"内容不能超过{self.MAX_LENGTH}字"}

        auth = self._auth()
        if mcp_token and auth:
            user = await auth.get_user_by_mcp_token(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        now = int(time.time())
        data = {
            "plugin_type": "microblog",
            "author_id": author_id,
            "title": "",
            "body": content,
            "status": visibility,
            "tags": "",
            "created_at": now,
            "updated_at": now,
        }
        record_id = await self.engine.put("contents", 0, data)
        return {"id": record_id, "created_at": now}

    async def list_posts(self, limit: int = 20, mcp_token: str = None) -> List[Dict]:
        sql = """
            SELECT c.*, u.username as author_name, u.avatar as author_avatar
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE c.plugin_type = 'microblog'
            ORDER BY c.created_at DESC
            LIMIT ?
        """
        rows = await self.engine.fetchall(sql, (limit,))
        for row in rows:
            if not row.get("author_name"):
                row["author_name"] = "匿名"
            row["content"] = row.pop("body", "")
        return rows

    async def delete_post(self, id: int, mcp_token: str = None) -> Dict:
        auth = self._auth()
        post = await self.engine.get("contents", id)
        if not post:
            return {"error": "微博不存在"}
        if mcp_token and auth:
            user = await auth.get_user_by_mcp_token(mcp_token)
            if user:
                if post.get("author_id") != user["id"] and user.get("role") != "admin":
                    return {"error": "无权删除"}
            else:
                return {"error": "无效的 Token"}
        await self.engine.delete("contents", id)
        return {"deleted": True}

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
        token = request.cookies.get("auth_token", "")
        if token:
            auth = self._auth()
            if auth:
                user = await auth.get_user_by_token(token)
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
        author_id = await self._get_author_id(request)
        return await self.create_post(content=content, author_id=author_id)

    async def delete_api(self, post_id: int, request, **kwargs):
        # 鉴权：只有作者或 admin 才能删除
        token = request.cookies.get("auth_token", "")
        auth = self._auth()
        current_user = None
        if token and auth:
            current_user = await auth.get_user_by_token(token)
        
        post = await self.engine.get("contents", post_id)
        if not post:
            return {"error": "微博不存在"}
        
        if not current_user:
            return {"error": "请先登录"}
        
        if post.get("author_id") != current_user["id"] and current_user.get("role") != "admin":
            return {"error": "无权限删除他人的微博"}
        
        await self.engine.delete("contents", post_id)
        return {"deleted": True}

    async def list_api(self, limit: int = 20, **kwargs):
        return await self.list_posts(limit=limit)
