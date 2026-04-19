"""Notes plugin implementation"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, MCPResource, Route
from starlette.responses import HTMLResponse


class NotesPlugin(Plugin):
    """Notes plugin - private notes for each user"""
    
    @property
    def name(self) -> str:
        return "notes"
    
    @property
    def version(self) -> str:
        return "0.1.0"
    
    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.config = ctx.config
        self.ctx = ctx
    
    def _get_auth_plugin(self):
        if self.ctx:
            return self.ctx.get_plugin("auth")
        return None
    
    def routes(self) -> List[Route]:
        return [
            Route("/notes", "GET", self.list_notes_page, "notes.list"),
            Route("/notes/new", "GET", self.new_note_page, "notes.new"),
            Route("/notes/edit/{note_id}", "GET", self.edit_note_page, "notes.edit"),
            Route("/notes", "POST", self.create_note_api, "notes.create"),
            Route("/notes/{note_id}", "GET", self.get_note_page, "notes.view"),
            Route("/notes/{note_id}", "PUT", self.update_note_api, "notes.update"),
            Route("/notes/{note_id}", "DELETE", self.delete_note_api, "notes.delete"),
            Route("/api/notes", "GET", self.list_my_notes_api, "notes.list_api"),
            Route("/api/notes/{note_id}", "GET", self.get_note_api, "notes.get_api"),
        ]
    
    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="create_note",
                description="Create a private note",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Note title"},
                        "content": {"type": "string", "description": "Note content (Markdown)"},
                        "visibility": {"type": "string", "enum": ["private", "public"], "default": "private"}
                    },
                    "required": ["title", "content"]
                },
                handler=self.create_note
            ),
            MCPTool(
                name="list_notes",
                description="List my notes (private notes only)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "visibility": {"type": "string", "enum": ["private", "public", "all"]},
                        "limit": {"type": "integer", "default": 20}
                    }
                },
                handler=self.list_notes
            ),
        ]
    
    # Auth helpers
    async def _get_current_user(self, request) -> Optional[Dict]:
        """Get current user from cookie"""
        token = request.cookies.get("auth_token", "")
        if not token:
            return None
        auth_plugin = self._get_auth_plugin()
        if auth_plugin:
            return await auth_plugin.get_user_by_token(token)
        return None
    
    async def _get_current_user_mcp(self, mcp_token: str = None) -> Optional[Dict]:
        """Get current user from MCP token"""
        if not mcp_token:
            return None
        auth_plugin = self._get_auth_plugin()
        if auth_plugin:
            return await auth_plugin.get_user_by_mcp_token(mcp_token)
        return None
    
    # Core methods
    async def create_note(
        self,
        title: str,
        content: str,
        visibility: str = "private",
        author_id: int = 1,
        mcp_token: str = None
    ) -> Dict[str, Any]:
        if mcp_token:
            user = await self._get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        now = int(time.time())
        
        # status: draft=草稿, published=已发布
        # visibility: private=私有, public=公开
        data = {
            "plugin_type": "note",
            "author_id": author_id,
            "title": title,
            "body": content,
            "status": "published",
            "visibility": visibility,
            "created_at": now,
            "updated_at": now
        }

        record_id = await self.engine.put("contents", 0, data)
        return {
            "id": record_id,
            "title": title,
            "visibility": visibility,
            "created_at": now
        }
    
    async def list_notes(
        self,
        visibility: str = "private",
        limit: int = 20,
        author_id: int = None,
        mcp_token: str = None
    ) -> List[Dict[str, Any]]:
        if mcp_token:
            user = await self._get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
        
        conditions = ["plugin_type = 'note'"]
        params = []
        
        if author_id:
            # 个人笔记：只能看自己的 + 公开的
            conditions.append("(author_id = ? OR visibility = 'public')")
            params.append(author_id)
        elif visibility == "private":
            # 未提供 author_id 且查询私有 → 空结果
            return []
        elif visibility == "public":
            conditions.append("visibility = 'public'")
        
        sql = f"""
            SELECT c.*, u.username as author_name, u.avatar as author_avatar
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE {' AND '.join(conditions)}
            ORDER BY c.updated_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        return await self.engine.fetchall(sql, tuple(params))
    
    async def update_note(
        self,
        note_id: int,
        title: str = None,
        content: str = None,
        visibility: str = None,
        author_id: int = None
    ) -> Dict[str, Any]:
        existing = await self.engine.get("contents", note_id)
        if not existing:
            return {"error": "笔记不存在"}
        
        # 权限检查：只能修改自己的笔记
        if author_id and existing.get("author_id") != author_id:
            return {"error": "无权修改此笔记"}
        
        if title:
            existing["title"] = title
        if content:
            existing["body"] = content
        if visibility:
            existing["visibility"] = visibility
        
        existing["updated_at"] = int(time.time())
        await self.engine.put("contents", note_id, existing)
        
        return {"id": note_id, "updated": True}
    
    async def delete_note(self, note_id: int, author_id: int = None, mcp_token: str = None) -> Dict[str, Any]:
        if mcp_token:
            user = await self._get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}
        existing = await self.engine.get("contents", note_id)
        if not existing:
            return {"error": "笔记不存在"}
        
        if author_id and existing.get("author_id") != author_id:
            return {"error": "无权删除此笔记"}
        
        await self.engine.delete("contents", note_id)
        return {"id": note_id, "deleted": True}

    async def update_note(self, note_id: int, title: str = None, content: str = None,
                          visibility: str = None, author_id: int = None, mcp_token: str = None) -> Dict[str, Any]:
        if mcp_token:
            user = await self._get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}
        existing = await self.engine.get("contents", note_id)
        if not existing:
            return {"error": "笔记不存在"}
        if author_id and existing.get("author_id") != author_id:
            return {"error": "无权修改此笔记"}
        
        now = int(time.time())
        data = {"updated_at": now}
        if title is not None:
            data["title"] = title
        if content is not None:
            data["body"] = content
        if visibility is not None:
            data["visibility"] = visibility
        
        await self.engine.put("contents", note_id, data)
        return {"id": note_id, "updated": True}

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        """MCP call dispatcher for notes plugin"""
        if tool_name == "create_note":
            return await self.create_note(mcp_token=mcp_token, **arguments)
        elif tool_name == "list_notes":
            return await self.list_notes(mcp_token=mcp_token, **arguments)
        elif tool_name == "update_note":
            return await self.update_note(mcp_token=mcp_token, **arguments)
        elif tool_name == "delete_note":
            return await self.delete_note(mcp_token=mcp_token, **arguments)
        raise ValueError(f"Unknown tool: {tool_name}")
    
    # HTTP handlers
    async def list_notes_page(self, request, **kwargs):
        """笔记列表页面"""
        user = await self._get_current_user(request)
        
        if user:
            notes = await self.list_notes(author_id=user["id"], limit=50)
        else:
            notes = await self.list_notes(visibility="public", limit=50)
        
        html = await self.ctx.template_engine.render("notes.html", {
            "nav_page": "notes",
            "notes": notes,
            "current_user": user
        })
        return HTMLResponse(content=html)
    
    async def new_note_page(self, request):
        """新建笔记页面"""
        user = await self._get_current_user(request)
        if not user:
            return HTMLResponse(content="<script>window.location.href='/login';</script>")
        
        html = await self.ctx.template_engine.render("new-note.html", {
            "nav_page": "notes",
            "is_edit": False,
            "note": {}
        })
        return HTMLResponse(content=html)
    
    async def edit_note_page(self, request, **kwargs):
        """编辑笔记页面"""
        from starlette.responses import HTMLResponse, RedirectResponse
        
        user = await self._get_current_user(request)
        if not user:
            return RedirectResponse(url="/login", status_code=302)
        
        note_id = int(kwargs.get("note_id", 0))
        note = await self.engine.get("contents", note_id)
        
        if not note or note.get("plugin_type") != "note":
            return HTMLResponse(content="<h1>笔记不存在</h1>", status_code=404)
        
        # 权限检查
        is_owner = user["id"] == note.get("author_id")
        is_admin = user.get("role") == "admin"
        if not is_owner and not is_admin:
            return HTMLResponse(content="<h1>无权编辑此笔记</h1>", status_code=403)
        
        html = await self.ctx.template_engine.render("new-note.html", {
            "nav_page": "notes",
            "note": note,
            "is_edit": True
        })
        return HTMLResponse(content=html)
    
    async def create_note_api(self, request, **kwargs):
        """创建笔记 API"""
        user = await self._get_current_user(request)
        if not user:
            return {"error": "请先登录", "code": "unauthorized"}
        
        # 解析表单或 JSON
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            body = await request.form()
        
        title = body.get("title", "").strip()
        content = body.get("content", "").strip()
        visibility = body.get("visibility", "private")
        
        if not title or not content:
            return {"error": "标题和内容不能为空"}
        
        return await self.create_note(
            title=title,
            content=content,
            visibility=visibility,
            author_id=user["id"]
        )
    
    async def get_note_api(self, note_id: int, request, **kwargs):
        """获取笔记详情"""
        user = await self._get_current_user(request)
        note = await self.engine.get("contents", note_id)
        
        if not note or note.get("plugin_type") != "note":
            return {"error": "笔记不存在"}
        
        # 权限检查
        is_owner = user and user["id"] == note.get("author_id")
        is_public = note.get("visibility") == "public"
        
        if not is_owner and not is_public:
            return {"error": "无权访问此笔记"}
        
        # 获取作者信息
        if note.get("author_id"):
            author = await self.engine.get("users", note["author_id"])
            if author:
                note["author_name"] = author.get("username", "匿名")
                note["author_avatar"] = author.get("avatar")
        
        note["is_owner"] = is_owner
        return note
    
    async def get_note_page(self, note_id: int, request, **kwargs):
        """笔记详情页面"""
        user = await self._get_current_user(request)
        note = await self.engine.get("contents", note_id)
        
        if not note or note.get("plugin_type") != "note":
            return HTMLResponse(content="<h1>笔记不存在</h1>", status_code=404)
        
        # 权限检查
        is_owner = user and user["id"] == note.get("author_id")
        is_public = note.get("visibility") == "public"
        
        if not is_owner and not is_public:
            return HTMLResponse(content="<h1>无权访问此笔记</h1>", status_code=403)
        
        # 获取作者信息
        if note.get("author_id"):
            author = await self.engine.get("users", note["author_id"])
            if author:
                note["author_name"] = author.get("username", "匿名")
                note["author_avatar"] = author.get("avatar")
        
        note["is_owner"] = is_owner
        
        html = await self.ctx.template_engine.render("note-view.html", {
            "nav_page": "notes",
            "note": note,
            "current_user": user
        })
        return HTMLResponse(content=html)
    
    async def update_note_api(self, note_id: int, request, **kwargs):
        """更新笔记 API"""
        user = await self._get_current_user(request)
        if not user:
            return {"error": "请先登录", "code": "unauthorized"}
        
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            body = await request.form()
        
        return await self.update_note(
            note_id=note_id,
            title=body.get("title"),
            content=body.get("content"),
            visibility=body.get("visibility"),
            author_id=user["id"]
        )
    
    async def delete_note_api(self, note_id: int, request, **kwargs):
        """删除笔记 API"""
        user = await self._get_current_user(request)
        if not user:
            return {"error": "请先登录", "code": "unauthorized"}
        
        return await self.delete_note(note_id=note_id, author_id=user["id"])
    
    async def list_my_notes_api(self, request, **kwargs):
        """获取我的笔记列表 API"""
        user = await self._get_current_user(request)
        if not user:
            return {"error": "请先登录", "code": "unauthorized"}
        
        return await self.list_notes(author_id=user["id"], limit=50)
