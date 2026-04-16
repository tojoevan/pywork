"""Blog plugin implementation"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, MCPResource, MCPPrompt, Route


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
        
        # Create blog-specific tables if needed
        # (contents table is shared, but we can add indexes)
    
    def routes(self) -> List[Route]:
        """HTTP routes"""
        return [
            Route("/blog/posts", "GET", self.list_posts, "blog.list_posts"),
            Route("/blog/posts", "POST", self.create_post_api, "blog.create_post"),
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
        author_id: int = 1
    ) -> Dict[str, Any]:
        """Create a blog post"""
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
        
        await self.engine.put("contents", 0, data)
        
        # Get the last inserted ID
        row = await self.engine.fetchone(
            "SELECT last_insert_rowid() as id"
        )
        
        return {
            "id": row["id"],
            "title": title,
            "status": status,
            "created_at": now
        }
    
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
            SELECT * FROM contents 
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
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
        
        return rows
    
    async def update_post(
        self,
        id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a blog post"""
        existing = await self.engine.get("contents", id)
        if not existing:
            return {"error": "Post not found"}
        
        if title:
            existing["title"] = title
        if content:
            existing["body"] = content
        if status:
            existing["status"] = status
        
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
    async def list_posts(self):
        """List posts API"""
        return await self.search_posts(limit=20)
    
    async def create_post_api(self, **kwargs):
        """Create post API"""
        return await self.create_post(**kwargs)
    
    async def get_post_api(self, post_id: int):
        """Get post API"""
        return await self.engine.get("contents", post_id)
    
    async def update_post_api(self, post_id: int, **kwargs):
        """Update post API"""
        kwargs["id"] = post_id
        return await self.update_post(**kwargs)
    
    async def delete_post_api(self, post_id: int):
        """Delete post API"""
        await self.engine.delete("contents", post_id)
        return {"deleted": True}
    
    async def search_posts_api(self, query: Optional[str] = None, tag: Optional[str] = None, status: Optional[str] = None, limit: int = 10):
        """Search posts API"""
        return await self.search_posts(query=query, tag=tag, status=status, limit=limit)
