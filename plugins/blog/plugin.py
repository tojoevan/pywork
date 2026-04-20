"""Blog plugin implementation"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, MCPResource, MCPPrompt, Route
from starlette.responses import HTMLResponse


class BlogPlugin(Plugin):
    """Blog plugin - proof of concept"""
    
    @property
    def name(self) -> str:
        return "blog"
    
    @property
    def version(self) -> str:
        return "0.1.0"
    
    async def init(self, ctx: PluginContext) -> None:
        """Initialize blog plugin"""
        self.engine = ctx.engine
        self.config = ctx.config
        self.ctx = ctx  # 保存 ctx 以便获取其他 plugin
        self._ctx = ctx  # 供基类鉴权方法使用
        
        # Create blog-specific tables if needed
        # (contents table is shared, but we can add indexes)
    
    def routes(self) -> List[Route]:
        """HTTP routes"""
        return [
            Route("/blog/new", "GET", self.new_post_page, "blog.new_post"),
            Route("/blog/edit/{post_id}", "GET", self.edit_post_page, "blog.edit_post"),
            Route("/blog/posts", "GET", self.list_posts, "blog.list_posts"),
            Route("/blog/posts", "POST", self.create_post_api, "blog.create_post"),
            Route("/blog/view/{post_id}", "GET", self.get_post_page, "blog.view_post"),
            Route("/blog/posts/{post_id}", "GET", self.get_post_api, "blog.get_post"),
            Route("/blog/posts/{post_id}", "PUT", self.update_post_api, "blog.update_post"),
            Route("/blog/posts/{post_id}", "DELETE", self.delete_post_api, "blog.delete_post"),
            Route("/blog/search", "GET", self.search_posts_api, "blog.search_posts"),
        ]
    
    def mcp_tools(self) -> List[MCPTool]:
        """MCP tools"""
        return [
            MCPTool(
                name="create_post",
                description="Create a blog post",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Post title"},
                        "content": {"type": "string", "description": "Post content (Markdown)"},
                        "status": {"type": "string", "enum": ["draft", "published"], "default": "draft"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["title", "content"]
                },
                handler=self.create_post
            ),
            MCPTool(
                name="search_posts",
                description="Search blog posts",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords"},
                        "tag": {"type": "string", "description": "Filter by tag"},
                        "status": {"type": "string", "enum": ["draft", "published"]},
                        "limit": {"type": "integer", "default": 10}
                    }
                },
                handler=self.search_posts
            ),
            MCPTool(
                name="update_post",
                description="Update a blog post",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Post ID"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["draft", "published"]}
                    },
                    "required": ["id"]
                },
                handler=self.update_post
            ),
            MCPTool(
                name="delete_post",
                description="Delete a blog post",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Post ID"}
                    },
                    "required": ["id"]
                },
                handler=self.delete_post_mcp
            ),
        ]
    
    def mcp_resources(self) -> List[MCPResource]:
        """MCP resources"""
        return [
            MCPResource(
                uri="blog://posts",
                name="All blog posts",
                mime_type="application/json",
                handler=self.list_all_posts
            ),
            MCPResource(
                uri="blog://posts/{id}",
                name="Post detail",
                mime_type="text/markdown",
                handler=self.get_post_resource
            ),
        ]
    
    def mcp_prompts(self) -> List[MCPPrompt]:
        """MCP prompts"""
        return [
            MCPPrompt(
                name="blog-writing-template",
                description="Blog writing template",
                template="""Write a blog post about: {{topic}}

Target audience: {{audience}}
Style: {{style}}

Requirements:
1. Engaging title
2. Clear structure with intro, body, conclusion
3. Use Markdown format
4. Include code examples if relevant
""",
                arguments=[
                    {"name": "topic", "description": "Article topic", "required": True},
                    {"name": "audience", "description": "Target audience", "required": False},
                    {"name": "style", "description": "Writing style", "required": False}
                ]
            ),
        ]
    
    # Core methods
    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        tags: Optional[List[str]] = None,
        author_id: int = 1,
        mcp_token: str = None
    ) -> Dict[str, Any]:
        """Create a blog post"""
        # 如果提供了 MCP token，验证并获取用户
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        now = int(time.time())

        data = {
            "plugin_type": "blog",
            "author_id": author_id,
            "title": title,
            "body": content,
            "status": status,
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "created_at": now,
            "updated_at": now
        }

        record_id = await self.engine.put("contents", 0, data)

        return {
            "id": record_id,
            "title": title,
            "status": status,
            "created_at": now
        }

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        """MCP 调用入口，处理认证"""
        if tool_name == "create_post":
            return await self.create_post(mcp_token=mcp_token, **arguments)
        elif tool_name == "search_posts":
            return await self.search_posts(**arguments)
        elif tool_name == "update_post":
            # 更新需要验证权限
            if mcp_token:
                user = await self.get_current_user_mcp(mcp_token)
                if user:
                    # 检查是否是作者或管理员
                    post = await self.engine.get("contents", arguments.get("id"))
                    if post and (post.get("author_id") == user["id"] or user.get("role") == "admin"):
                        return await self.update_post(**arguments)
                    return {"error": "无权修改此文章"}
                return {"error": "无效的 MCP Token"}
            return {"error": "需要 MCP Token 进行认证"}
        elif tool_name == "delete_post":
            if mcp_token:
                user = await self.get_current_user_mcp(mcp_token)
                if user:
                    post = await self.engine.get("contents", arguments.get("id"))
                    if post and (post.get("author_id") == user["id"] or user.get("role") == "admin"):
                        return await self.delete_post_mcp(**arguments)
                    return {"error": "无权删除此文章"}
                return {"error": "无效的 MCP Token"}
            return {"error": "需要 MCP Token 进行认证"}
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
    
    async def search_posts(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search blog posts"""
        conditions = ["plugin_type = 'blog'"]
        params = []
        
        if query:
            # Use FTS for full-text search
            conditions.append("id IN (SELECT rowid FROM contents_fts WHERE contents_fts MATCH ?)")
            params.append(query)
        
        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        sql = f"""
            SELECT 
                c.*,
                u.username as author_name,
                u.avatar as author_avatar
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE {' AND '.join(conditions)}
            ORDER BY c.created_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = await self.engine.fetchall(sql, tuple(params))
        
        # Parse tags JSON
        for row in rows:
            if row.get("tags"):
                try:
                    row["tags"] = json.loads(row["tags"])
                except:
                    pass
            # 确保作者信息存在
            if not row.get("author_name"):
                row["author_name"] = "匿名"
        
        return rows
    
    async def update_post(
        self,
        id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Update a blog post"""
        existing = await self.engine.get("contents", id)
        if not existing:
            return {"error": "Post not found"}
        
        if title is not None:
            existing["title"] = title
        if content is not None:
            existing["body"] = content
        if status is not None:
            existing["status"] = status
        if tags is not None:
            if isinstance(tags, list):
                existing["tags"] = json.dumps(tags, ensure_ascii=False)
            elif isinstance(tags, str):
                existing["tags"] = tags
        
        existing["updated_at"] = int(time.time())
        
        await self.engine.put("contents", id, existing)
        
        return {"id": id, "updated": True}
    
    async def delete_post_mcp(self, id: int) -> Dict[str, Any]:
        """Delete a blog post (MCP handler)"""
        await self.engine.delete("contents", id)
        return {"id": id, "deleted": True}
    
    async def list_all_posts(self) -> str:
        """List all posts (MCP resource)"""
        posts = await self.search_posts(limit=100)
        return json.dumps(posts, ensure_ascii=False, indent=2)
    
    async def get_post_resource(self, id: int) -> str:
        """Get post as markdown (MCP resource)"""
        post = await self.engine.get("contents", id)
        if not post:
            return "# Post not found"
        
        return f"""# {post['title']}

**Status:** {post['status']}  
**Created:** {post['created_at']}

---

{post['body']}
"""
    
    # HTTP API handlers (FastAPI style)
    async def list_posts(self, **kwargs):
        """List posts API"""
        return await self.search_posts(limit=20)
    
    async def new_post_page(self, request):
        """新建博客页面"""
        html = await self.ctx.template_engine.render("new.html", {
            "nav_page": "blog",
            "is_edit": False,
            "post": {}
        })
        return HTMLResponse(content=html)
    
    async def get_post_page(self, request, **kwargs):
        """博客详情页面（HTML）"""
        post_id = int(kwargs.get("post_id", 0))
        post = await self.engine.get("contents", post_id)
        if not post or post.get("plugin_type") != "blog":
            from starlette.responses import HTMLResponse
            return HTMLResponse(content="<h1>文章不存在</h1>", status_code=404)
        
        # 解析 tags
        if post.get("tags"):
            try:
                post["tags"] = json.loads(post["tags"])
            except:
                post["tags"] = []
        
        # 获取作者信息
        author_id = post.get("author_id")
        if author_id:
            author = await self.engine.get("users", author_id)
            if author:
                post["author_name"] = author.get("username", "匿名")
                post["author_avatar"] = author.get("avatar")
        
        # 获取当前用户（用于判断是否显示编辑按钮）
        current_user = await self.get_current_user(request)
        
        
        html = await self.ctx.template_engine.render("post.html", {
            "nav_page": "blog",
            "post": post,
            "current_user": current_user
        })
        from starlette.responses import HTMLResponse
        return HTMLResponse(content=html)
    
    async def edit_post_page(self, request, **kwargs):
        """编辑博客页面"""
        from starlette.responses import HTMLResponse, RedirectResponse
        
        # 检查登录
        current_user = await self.get_current_user(request)
        
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        
        # 获取博客内容
        post_id = int(kwargs.get("post_id", 0))
        post = await self.engine.get("contents", post_id)
        if not post or post.get("plugin_type") != "blog":
            return HTMLResponse(content="<h1>文章不存在</h1>", status_code=404)
        
        # 权限检查：作者或管理员
        is_author = post.get("author_id") == current_user["id"]
        is_admin = current_user.get("role") == "admin"
        if not is_author and not is_admin:
            return HTMLResponse(content="<h1>无权编辑此文章</h1>", status_code=403)
        
        # 解析 tags
        if post.get("tags"):
            try:
                post["tags"] = json.loads(post["tags"])
            except:
                post["tags"] = []
        
        html = await self.ctx.template_engine.render("new.html", {
            "nav_page": "blog",
            "post": post,  # 预填充数据
            "is_edit": True
        })
        return HTMLResponse(content=html)
    
    async def create_post_api(self, request, **kwargs):
        """Create post API"""
        # 解析请求体
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            body = await request.form()
        
        title = body.get("title", "").strip() if isinstance(body.get("title"), str) else body.get("title", "")
        content = body.get("body", body.get("content", "")).strip() if isinstance(body.get("body") or body.get("content"), str) else body.get("body", body.get("content", ""))
        status = body.get("status", "draft")
        tags = body.get("tags", [])
        
        if not title or not content:
            return {"error": "标题和内容不能为空"}
        
        # 获取当前用户
        author_id = 1  # 默认作者
        user = await self.get_current_user(request)
        if user:
            author_id = user["id"]
        
        return await self.create_post(
            title=title,
            content=content,
            status=status,
            tags=tags if isinstance(tags, list) else [],
            author_id=author_id
        )
    
    async def get_post_api(self, post_id: int, **kwargs):
        """Get post API"""
        post = await self.engine.get("contents", post_id)
        if not post:
            return None
            
        # 解析 tags
        if post.get("tags"):
            try:
                post["tags"] = json.loads(post["tags"])
            except:
                pass
        
        # 获取作者信息
        if post.get("author_id"):
            user = await self.engine.get("users", post["author_id"])
            if user:
                post["author_name"] = user.get("username", "匿名")
                post["author_avatar"] = user.get("avatar")
            else:
                post["author_name"] = "匿名"
        else:
            post["author_name"] = "匿名"
            
        return post
    
    async def update_post_api(self, post_id: int, request=None, **kwargs):
        """Update post API"""
        # 解析请求体，兼容 body/content 字段名
        data = kwargs
        if request:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.json()
                    data = body
                except Exception:
                    pass

        title = data.get("title")
        content = data.get("body", data.get("content"))
        status = data.get("status")
        tags = data.get("tags")

        return await self.update_post(id=post_id, title=title, content=content, status=status, tags=tags)
    
    async def delete_post_api(self, post_id: int, request=None, **kwargs):
        """Delete post API"""
        # 鉴权：检查用户是否登录
        user = await self.get_current_user(request)
        if not user:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "请先登录"}, status_code=401)
        
        # 获取文章，检查权限
        post = await self.engine.get("contents", post_id)
        if not post:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "文章不存在"}, status_code=404)
        
        # 只有作者或管理员可以删除
        if post.get("author_id") != user["id"] and user.get("role") != "admin":
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "无权删除此文章"}, status_code=403)
        
        await self.engine.delete("contents", post_id)
        return {"deleted": True}
    
    async def search_posts_api(self, query: Optional[str] = None, tag: Optional[str] = None, status: Optional[str] = None, limit: int = 10, **kwargs):
        """Search posts API"""
        return await self.search_posts(query=query, tag=tag, status=status, limit=limit)
