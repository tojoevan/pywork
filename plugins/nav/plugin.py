"""Navigation / Bookmark plugin - minimalist URL collection"""
from typing import List, Dict, Any, Optional
import time
import json

from app.plugin import Plugin, PluginContext, MCPTool, Route
from starlette.responses import HTMLResponse


class NavPlugin(Plugin):
    """Navigation plugin - collect and display bookmarks with tag aggregation"""

    @property
    def name(self) -> str:
        return "nav"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.config = ctx.config
        self.ctx = ctx
        self._ctx = ctx
        await self._ensure_tables()

    async def _ensure_tables(self) -> None:
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS nav_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT DEFAULT '',
            icon TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            visibility TEXT DEFAULT 'public',
            author_id INTEGER NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS nav_link_hides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            link_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(user_id, link_id)
        )
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_nav_links_author ON nav_links(author_id)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_nav_links_visibility ON nav_links(visibility)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_nav_link_hides_user ON nav_link_hides(user_id)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_nav_link_hides_link ON nav_link_hides(link_id)
        """)

    def routes(self) -> List[Route]:
        return [
            Route("/nav", "GET", self.nav_page, "nav.page"),
            Route("/nav", "POST", self.create_link_api, "nav.create"),
            Route("/nav/{link_id}", "PUT", self.update_link_api, "nav.update"),
            Route("/nav/{link_id}", "DELETE", self.delete_link_api, "nav.delete"),
            Route("/nav/{link_id}/hide", "POST", self.hide_link_api, "nav.hide"),
            Route("/nav/{link_id}/hide", "DELETE", self.unhide_link_api, "nav.unhide"),
            Route("/api/nav", "GET", self.list_links_api, "nav.list_api"),
        ]

    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="create_nav_link",
                description="Add a bookmark to the navigation page",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Bookmark title"},
                        "url": {"type": "string", "description": "URL"},
                        "description": {"type": "string", "description": "Short description"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                        "visibility": {"type": "string", "enum": ["public", "private"], "default": "public"},
                    },
                    "required": ["title", "url"]
                },
                handler=self.create_link
            ),
            MCPTool(
                name="list_nav_links",
                description="List bookmarks from the navigation page",
                input_schema={
                    "type": "object",
                    "properties": {
                        "visibility": {"type": "string", "enum": ["public", "private", "all"], "default": "public"},
                        "tag": {"type": "string", "description": "Filter by tag"},
                        "limit": {"type": "integer", "default": 100}
                    }
                },
                handler=self.list_links
            ),
            MCPTool(
                name="delete_nav_link",
                description="Delete a bookmark from the navigation page",
                input_schema={
                    "type": "object",
                    "properties": {
                        "link_id": {"type": "integer", "description": "Bookmark ID to delete"}
                    },
                    "required": ["link_id"]
                },
                handler=self.delete_link
            ),
        ]

    # ============================================================
    #  Core data methods
    # ============================================================

    async def list_links(
        self,
        visibility: str = "public",
        tag: str = None,
        limit: int = 100,
        author_id: int = None,
        exclude_hidden_for: int = None,
        mcp_token: str = None,
    ) -> List[Dict[str, Any]]:
        """List bookmarks with optional filters"""
        conditions = []
        params = []

        if visibility == "public":
            conditions.append("visibility = 'public'")
        elif visibility == "private" and author_id:
            conditions.append("visibility = 'private'")
            conditions.append("author_id = ?")
            params.append(author_id)
        # "all" = no visibility filter

        if author_id and visibility != "private":
            conditions.append("author_id = ?")
            params.append(author_id)

        if tag:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')

        # Exclude hidden links for a specific user
        if exclude_hidden_for:
            conditions.append(f"id NOT IN (SELECT link_id FROM nav_link_hides WHERE user_id = ?)")
            params.append(exclude_hidden_for)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM nav_links WHERE {where} ORDER BY sort_order ASC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.engine.fetchall(sql, tuple(params))
        links = []
        for row in rows:
            link = dict(row)
            link["tags"] = json.loads(link.get("tags", "[]") or "[]")
            links.append(link)
        return links

    async def create_link(
        self,
        title: str,
        url: str,
        description: str = "",
        tags: List[str] = None,
        visibility: str = "public",
        author_id: int = 1,
        mcp_token: str = None,
    ) -> Dict[str, Any]:
        """Create a new bookmark"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]

        now = int(time.time())
        link_id = await self.engine.put("nav_links", 0, {
            "title": title,
            "url": url,
            "description": description or "",
            "icon": "",
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "visibility": visibility,
            "author_id": author_id,
            "sort_order": 0,
            "created_at": now,
            "updated_at": now,
        })
        return {"id": link_id, "title": title, "url": url}

    async def update_link(
        self,
        link_id: int,
        title: str = None,
        url: str = None,
        description: str = None,
        tags: List[str] = None,
        visibility: str = None,
        user_id: int = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """Update a bookmark (author or admin only)"""
        existing = await self.engine.get("nav_links", link_id)
        if not existing:
            return {"error": "Bookmark not found"}

        if user_id and existing["author_id"] != user_id and not is_admin:
            return {"error": "Permission denied"}

        now = int(time.time())
        data = dict(existing)
        if title is not None:
            data["title"] = title
        if url is not None:
            data["url"] = url
        if description is not None:
            data["description"] = description
        if tags is not None:
            data["tags"] = json.dumps(tags, ensure_ascii=False)
        if visibility is not None:
            data["visibility"] = visibility
        data["updated_at"] = now

        await self.engine.put("nav_links", link_id, data)
        return {"id": link_id, "ok": True}

    async def delete_link(
        self,
        link_id: int,
        user_id: int = None,
        is_admin: bool = False,
        mcp_token: str = None,
    ) -> Dict[str, Any]:
        """Delete a bookmark (author or admin only)"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                user_id = user["id"]
                is_admin = user.get("role") == "admin"

        existing = await self.engine.get("nav_links", link_id)
        if not existing:
            return {"error": "Bookmark not found"}

        if user_id and existing["author_id"] != user_id and not is_admin:
            return {"error": "Permission denied"}

        await self.engine.delete("nav_links", link_id)
        # Also clean up hide records
        await self.engine.execute(
            "DELETE FROM nav_link_hides WHERE link_id = ?", (link_id,)
        )
        return {"id": link_id, "ok": True}

    async def hide_link(self, user_id: int, link_id: int) -> Dict[str, Any]:
        """Hide a public bookmark for a user"""
        now = int(time.time())
        try:
            await self.engine.execute(
                "INSERT OR IGNORE INTO nav_link_hides (user_id, link_id, created_at) VALUES (?, ?, ?)",
                (user_id, link_id, now)
            )
        except Exception:
            pass
        return {"ok": True}

    async def unhide_link(self, user_id: int, link_id: int) -> Dict[str, Any]:
        """Unhide a bookmark for a user"""
        await self.engine.execute(
            "DELETE FROM nav_link_hides WHERE user_id = ? AND link_id = ?",
            (user_id, link_id)
        )
        return {"ok": True}

    async def get_hidden_ids(self, user_id: int) -> set:
        """Get set of link IDs hidden by a user"""
        rows = await self.engine.fetchall(
            "SELECT link_id FROM nav_link_hides WHERE user_id = ?", (user_id,)
        )
        return {r["link_id"] for r in rows}

    # ============================================================
    #  HTTP handlers
    # ============================================================

    async def nav_page(self, request, **kwargs):
        """Render the navigation page"""
        user = await self.get_current_user(request)
        user_id = user["id"] if user else None
        is_admin = user and user.get("role") == "admin"

        # Get public links (excluding hidden ones for logged-in users)
        public_links = await self.list_links(
            visibility="public",
            exclude_hidden_for=user_id,
        )

        # Get user's private links
        private_links = []
        if user_id:
            private_links = await self.list_links(
                visibility="private",
                author_id=user_id,
            )

        # Aggregate by tag
        tagged = {}  # tag -> [links]
        untagged = []

        for link in public_links + private_links:
            tags = link.get("tags", [])
            if not tags:
                untagged.append(link)
            else:
                for tag in tags:
                    tagged.setdefault(tag, []).append(link)

        # Build groups: sorted by tag name, untagged at the end
        groups = []
        for tag in sorted(tagged.keys()):
            groups.append({"tag": tag, "links": tagged[tag]})
        if untagged:
            groups.append({"tag": "", "links": untagged})

        # Get hidden link IDs for the hide toggle
        hidden_ids = set()
        if user_id:
            hidden_ids = await self.get_hidden_ids(user_id)

        html = await self.ctx.template_engine.render("nav.html", {
            "nav_page": "nav",
            "groups": groups,
            "user": user,
            "is_admin": is_admin,
            "hidden_ids": hidden_ids,
            "public_links": public_links,
        })
        return HTMLResponse(content=html)

    async def create_link_api(self, request, **kwargs):
        """POST /nav - create a bookmark"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("Login required", 401)

        data = kwargs
        title = (data.get("title") or "").strip()
        url = (data.get("url") or "").strip()
        if not title or not url:
            return self.error_json("Title and URL are required", 400)

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        description = (data.get("description") or "").strip()
        visibility = data.get("visibility", "public")
        if visibility not in ("public", "private"):
            visibility = "public"

        # Parse tags
        tags_raw = data.get("tags", "")
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.replace("，", ",").split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags = []

        result = await self.create_link(
            title=title, url=url, description=description,
            tags=tags, visibility=visibility, author_id=user["id"]
        )
        return result

    async def update_link_api(self, request, **kwargs):
        """PUT /nav/{link_id} - update a bookmark"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("Login required", 401)

        link_id = kwargs.get("link_id")
        if not link_id:
            return self.error_json("Missing link_id", 400)

        data = kwargs
        title = data.get("title")
        url = data.get("url")
        description = data.get("description")
        visibility = data.get("visibility")

        tags_raw = data.get("tags")
        tags = None
        if tags_raw is not None:
            if isinstance(tags_raw, str):
                tags = [t.strip() for t in tags_raw.replace("，", ",").split(",") if t.strip()]
            elif isinstance(tags_raw, list):
                tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        result = await self.update_link(
            link_id=int(link_id),
            title=title, url=url, description=description,
            tags=tags, visibility=visibility,
            user_id=user["id"], is_admin=(user.get("role") == "admin")
        )
        return result

    async def delete_link_api(self, request, **kwargs):
        """DELETE /nav/{link_id} - delete a bookmark"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("Login required", 401)

        link_id = kwargs.get("link_id")
        if not link_id:
            return self.error_json("Missing link_id", 400)

        result = await self.delete_link(
            link_id=int(link_id),
            user_id=user["id"],
            is_admin=(user.get("role") == "admin")
        )
        return result

    async def hide_link_api(self, request, **kwargs):
        """POST /nav/{link_id}/hide - hide a bookmark"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("Login required", 401)

        link_id = kwargs.get("link_id")
        if not link_id:
            return self.error_json("Missing link_id", 400)

        return await self.hide_link(user["id"], int(link_id))

    async def unhide_link_api(self, request, **kwargs):
        """DELETE /nav/{link_id}/hide - unhide a bookmark"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("Login required", 401)

        link_id = kwargs.get("link_id")
        if not link_id:
            return self.error_json("Missing link_id", 400)

        return await self.unhide_link(user["id"], int(link_id))

    async def list_links_api(self, request, **kwargs):
        """GET /api/nav - list bookmarks as JSON"""
        user = await self.get_current_user(request)
        user_id = user["id"] if user else None

        visibility = kwargs.get("visibility", "public")
        tag = kwargs.get("tag")
        limit = int(kwargs.get("limit", 100))

        if visibility == "private" and not user_id:
            return {"links": []}

        links = await self.list_links(
            visibility=visibility,
            tag=tag,
            limit=limit,
            author_id=user_id if visibility == "private" else None,
            exclude_hidden_for=user_id,
        )
        return {"links": links}
