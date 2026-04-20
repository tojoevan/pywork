"""About page plugin with guestbook (admin-moderated comments)"""
import time
from typing import List, Dict, Any, Optional

from app.plugin import Plugin, PluginContext, MCPTool, Route


class AboutPlugin(Plugin):

    @property
    def name(self) -> str:
        return "about"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.template_engine = ctx.template_engine
        self.ctx = ctx
        self._ctx = ctx  # 供基类鉴权方法使用

    def routes(self) -> List[Route]:
        return [
            Route("/about", "GET", self.about_page, "about.page"),
            Route("/about/comments", "POST", self.submit_comment, "about.submit"),
            Route("/about/comments/{comment_id}/approve", "POST", self.approve_comment, "about.approve"),
            Route("/about/comments/{comment_id}", "DELETE", self.delete_comment, "about.delete"),
            Route("/about/admin/comments", "GET", self.admin_comments, "about.admin"),
        ]

    # === 页面 ===

    async def about_page(self, request, **kwargs):
        """关于页面"""
        from starlette.responses import HTMLResponse

        # 获取已审核通过的留言
        comments = await self._list_approved_comments()
        current_user = await self.get_current_user(request)

        html = await self.template_engine.render(
            "about.html",
            {
                "nav_page": "about",
                "comments": comments,
                "current_user": current_user,
            }
        )
        return HTMLResponse(content=html)

    async def admin_comments(self, request, **kwargs):
        """管理员留言审核页面"""
        from starlette.responses import HTMLResponse

        if not await self.is_admin(request):
            return HTMLResponse(content="<h1>403 Forbidden</h1>", status_code=403)

        pending = await self._list_pending_comments()
        approved = await self._list_approved_comments()

        html = await self.template_engine.render(
            "admin_comments.html",
            {
                "nav_page": "about",
                "pending_comments": pending,
                "approved_comments": approved,
            }
        )
        return HTMLResponse(content=html)

    # === API ===

    async def submit_comment(self, request, **kwargs):
        """提交留言"""
        import json

        # 解析请求数据
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        nickname = (body.get("nickname") or "").strip()[:50]
        email = (body.get("email") or "").strip()[:100]
        content = (body.get("content") or "").strip()[:1000]

        if not content:
            return {"error": "留言内容不能为空"}
        if not email:
            return {"error": "邮箱地址不能为空"}
        import re
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            return {"error": "请输入有效的邮箱地址"}
        if not nickname:
            nickname = "匿名"

        # 获取当前登录用户（可选）
        current_user = await self.get_current_user(request)
        author_id = current_user["id"] if current_user else 0

        now = int(time.time())
        data = {
            "tenant_id": 0,
            "plugin_type": "guestbook",
            "author_id": author_id,
            "title": nickname,
            "body": content,
            "meta_json": json.dumps({"nickname": nickname, "email": email}),
            "tags": "",
            "created_at": now,
            "updated_at": now,
            "status": "pending",  # 待审核
        }
        record_id = await self.engine.put("contents", 0, data)

        return {"id": record_id, "status": "pending", "message": "留言已提交，等待管理员审核"}

    async def approve_comment(self, comment_id: int, request, **kwargs):
        """审核通过留言"""
        if not await self.is_admin(request):
            return {"error": "无权限操作"}

        comment = await self.engine.get("contents", comment_id)
        if not comment or comment.get("plugin_type") != "guestbook":
            return {"error": "留言不存在"}

        comment["status"] = "public"
        await self.engine.put("contents", comment_id, comment)
        return {"approved": True}

    async def delete_comment(self, comment_id: int, request, **kwargs):
        """删除留言（管理员）"""
        if not await self.is_admin(request):
            return {"error": "无权限操作"}

        comment = await self.engine.get("contents", comment_id)
        if not comment or comment.get("plugin_type") != "guestbook":
            return {"error": "留言不存在"}

        await self.engine.delete("contents", comment_id)
        return {"deleted": True}

    # === 数据查询 ===

    async def _list_approved_comments(self) -> List[Dict]:
        """获取已审核通过的留言"""
        sql = """
            SELECT c.id, c.title as nickname, c.body as content, c.created_at,
                   c.author_id, u.username, u.avatar
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE c.plugin_type = 'guestbook' AND c.status = 'public'
            ORDER BY c.created_at DESC
        """
        rows = await self.engine.fetchall(sql)
        for row in rows:
            if not row.get("nickname"):
                # 尝试从 meta_json 获取
                import json
                try:
                    meta = json.loads(row.get("meta_json") or "{}")
                    row["nickname"] = meta.get("nickname", "匿名")
                except:
                    row["nickname"] = "匿名"
        return rows

    async def _list_pending_comments(self) -> List[Dict]:
        """获取待审核留言"""
        sql = """
            SELECT c.id, c.title as nickname, c.body as content, c.created_at,
                   c.author_id, u.username, u.avatar
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE c.plugin_type = 'guestbook' AND c.status = 'pending'
            ORDER BY c.created_at DESC
        """
        rows = await self.engine.fetchall(sql)
        for row in rows:
            if not row.get("nickname"):
                import json
                try:
                    meta = json.loads(row.get("meta_json") or "{}")
                    row["nickname"] = meta.get("nickname", "匿名")
                except:
                    row["nickname"] = "匿名"
        return rows

    # === MCP ===

    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="submit_guestbook",
                description="提交关于页面留言",
                input_schema={
                    "type": "object",
                    "properties": {
                        "nickname": {"type": "string", "description": "昵称"},
                        "content": {"type": "string", "description": "留言内容"},
                    },
                    "required": ["content"]
                },
                handler=self.submit_comment,
            ),
        ]

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        if tool_name == "submit_guestbook":
            return await self.submit_comment(nickname=arguments.get("nickname", ""), content=arguments.get("content", ""))
