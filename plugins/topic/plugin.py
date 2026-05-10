"""Topic Discussion plugin - structured discussion with voting and AI summarization"""
from typing import List, Dict, Any, Optional
import time

from app.plugin import Plugin, PluginContext, MCPTool, Route
from starlette.responses import HTMLResponse


class TopicPlugin(Plugin):
    """Topic Discussion plugin - structured discussion topics with voting and AI summarization"""

    @property
    def name(self) -> str:
        return "topic"

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
        """Create topic-related tables if not exists"""
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS topic_discussions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            deadline INTEGER NOT NULL,
            summary TEXT DEFAULT '',
            summary_post_id INTEGER DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            raft_term INTEGER DEFAULT 0,
            raft_index INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1,
            node_id TEXT DEFAULT 'local'
        )
        """)
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS topic_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS topic_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE(target_type, target_id, author_id)
        )
        """)
        # Indexes
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_discussions_status ON topic_discussions(status)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_discussions_deadline ON topic_discussions(deadline)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_replies_topic ON topic_replies(topic_id)
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_votes_target ON topic_votes(target_type, target_id)
        """)

    def routes(self) -> List[Route]:
        return [
            Route("/topic", "GET", self.topic_list_page, "topic.list"),
            Route("/topic/new", "GET", self.new_topic_page, "topic.new"),
            Route("/topic/{topic_id}/edit", "GET", self.edit_topic_page, "topic.edit"),
            Route("/topic/{topic_id}", "GET", self.topic_detail_page, "topic.detail"),
            Route("/api/topic", "POST", self.create_topic_api, "topic.create_api"),
            Route("/api/topic/{topic_id}", "PUT", self.update_topic_api, "topic.update_api"),
            Route("/api/topic/{topic_id}/reply", "POST", self.reply_topic_api, "topic.reply_api"),
            Route("/api/topic/{topic_id}/vote", "POST", self.vote_api, "topic.vote_api"),
            Route("/api/topic/{topic_id}/close", "POST", self.close_topic_api, "topic.close_api"),
            Route("/api/topic/{topic_id}/summarize", "POST", self.summarize_topic_api, "topic.summarize_api"),
            Route("/api/topic/check-expired", "POST", self.check_expired_api, "topic.check_expired"),
        ]

    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="create_topic",
                description="Create a discussion topic with title, description and deadline",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Topic title"},
                        "description": {"type": "string", "description": "Topic description"},
                        "deadline_hours": {"type": "integer", "description": "Hours until discussion deadline", "default": 72}
                    },
                    "required": ["title"]
                },
                handler=self.create_topic
            ),
            MCPTool(
                name="update_topic",
                description="Update an existing discussion topic (title, description, deadline)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "integer", "description": "Topic ID to update"},
                        "title": {"type": "string", "description": "New topic title"},
                        "description": {"type": "string", "description": "New topic description"},
                        "deadline_hours": {"type": "integer", "description": "New hours until discussion deadline (from now)"}
                    },
                    "required": ["topic_id"]
                },
                handler=self.update_topic
            ),
            MCPTool(
                name="list_topics",
                description="List discussion topics with optional status filter",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["open", "closed", "summarized", "all"], "default": "all"},
                        "limit": {"type": "integer", "default": 20},
                        "offset": {"type": "integer", "default": 0}
                    }
                },
                handler=self.list_topics
            ),
            MCPTool(
                name="reply_topic",
                description="Reply to a discussion topic",
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "integer", "description": "Topic ID"},
                        "content": {"type": "string", "description": "Reply content"},
                        "parent_id": {"type": "integer", "description": "Parent reply ID for nested replies (optional)"}
                    },
                    "required": ["topic_id", "content"]
                },
                handler=self.reply_topic
            ),
            MCPTool(
                name="vote",
                description="Vote (upvote or downvote) on a topic or reply",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_type": {"type": "string", "enum": ["topic", "reply"], "description": "Vote target type"},
                        "target_id": {"type": "integer", "description": "Target ID"},
                        "vote_type": {"type": "string", "enum": ["upvote", "downvote"], "description": "Vote type"}
                    },
                    "required": ["target_type", "target_id", "vote_type"]
                },
                handler=self.vote
            ),
            MCPTool(
                name="get_topic_detail",
                description="Get detailed information about a topic including replies and vote counts",
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "integer", "description": "Topic ID"}
                    },
                    "required": ["topic_id"]
                },
                handler=self.get_topic_detail
            ),
            MCPTool(
                name="summarize_topic",
                description="Summarize a closed topic using LLM and optionally publish as blog post",
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "integer", "description": "Topic ID to summarize"},
                        "publish_blog": {"type": "boolean", "description": "Whether to publish summary as blog post", "default": True}
                    },
                    "required": ["topic_id"]
                },
                handler=self.summarize_topic_mcp
            ),
        ]

    # ========================================================
    #  Core methods
    # ========================================================

    async def create_topic(
        self,
        title: str,
        description: str = "",
        deadline_hours: int = 72,
        author_id: int = 1,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new discussion topic"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        now = int(time.time())
        deadline = now + deadline_hours * 3600

        data = {
            "author_id": author_id,
            "title": title,
            "description": description,
            "status": "open",
            "deadline": deadline,
            "summary": "",
            "summary_post_id": None,
            "created_at": now,
            "updated_at": now,
        }

        record_id = await self.engine.put("topic_discussions", 0, data)
        return {
            "id": record_id,
            "title": title,
            "status": "open",
            "deadline": deadline,
            "deadline_hours": deadline_hours,
            "created_at": now
        }

    async def update_topic(
        self,
        topic_id: int,
        title: str = None,
        description: str = None,
        deadline_hours: int = None,
        author_id: int = None,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update an existing discussion topic"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return {"error": "话题不存在"}

        # Only author or admin can edit
        if author_id and topic["author_id"] != author_id:
            # Check admin role via user lookup
            user_row = await self.engine.fetchone(
                "SELECT role FROM users WHERE id = ?", (author_id,)
            )
            if not user_row or user_row["role"] != "admin":
                return {"error": "无权编辑此话题"}

        # Only allow editing open topics
        if topic["status"] not in ("open",):
            return {"error": "只能编辑进行中的话题"}

        now = int(time.time())
        updates = {"updated_at": now}

        if title is not None:
            title = title.strip()
            if not title:
                return {"error": "标题不能为空"}
            updates["title"] = title

        if description is not None:
            updates["description"] = description

        if deadline_hours is not None:
            updates["deadline"] = now + deadline_hours * 3600

        await self.engine.put("topic_discussions", topic_id, updates)

        # Fetch updated topic
        updated = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        return dict(updated)

    async def list_topics(
        self,
        status: str = "all",
        limit: int = 20,
        offset: int = 0,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """List discussion topics"""
        now = int(time.time())

        # Auto-mark expired open topics as closed
        await self._mark_expired_topics()

        conditions = []
        params = []

        if status != "all":
            conditions.append("t.status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = f"""
            SELECT t.*,
                   COALESCE(u.nickname, u.display_name, u.username) as author_name,
                   u.avatar as author_avatar,
                   (SELECT COUNT(*) FROM topic_replies r WHERE r.topic_id = t.id) as reply_count,
                   (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'topic' AND v.target_id = t.id AND v.vote_type = 'upvote') as upvote_count,
                   (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'topic' AND v.target_id = t.id AND v.vote_type = 'downvote') as downvote_count
            FROM topic_discussions t
            LEFT JOIN users u ON t.author_id = u.id
            {where_clause}
            ORDER BY t.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = await self.engine.fetchall(sql, tuple(params))

        # Add remaining time info
        for row in rows:
            row["is_expired"] = row["deadline"] < now and row["status"] == "open"
            if row["status"] == "open" and row["deadline"] > now:
                remaining = row["deadline"] - now
                row["remaining_hours"] = round(remaining / 3600, 1)
            else:
                row["remaining_hours"] = 0

        return rows

    async def reply_topic(
        self,
        topic_id: int,
        content: str,
        parent_id: int = None,
        author_id: int = 1,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Reply to a discussion topic"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        # Check topic exists and is open
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return {"error": "话题不存在"}
        if topic["status"] == "closed" or topic["status"] == "summarized":
            return {"error": "话题已结束，无法回复"}

        now = int(time.time())
        data = {
            "topic_id": topic_id,
            "author_id": author_id,
            "content": content,
            "parent_id": parent_id,
            "created_at": now,
            "updated_at": now,
        }

        record_id = await self.engine.put("topic_replies", 0, data)

        # Update topic updated_at
        await self.engine.execute(
            "UPDATE topic_discussions SET updated_at = ? WHERE id = ?",
            (now, topic_id)
        )

        return {
            "id": record_id,
            "topic_id": topic_id,
            "content": content,
            "created_at": now
        }

    async def vote(
        self,
        target_type: str,
        target_id: int,
        vote_type: str,
        author_id: int = 1,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Vote on a topic or reply (upvote/downvote)"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if user:
                author_id = user["id"]
            else:
                return {"error": "无效的 MCP Token"}

        # Check for existing vote
        existing = await self.engine.fetchone(
            "SELECT * FROM topic_votes WHERE target_type = ? AND target_id = ? AND author_id = ?",
            (target_type, target_id, author_id)
        )

        now = int(time.time())

        if existing:
            if existing["vote_type"] == vote_type:
                # Remove vote (toggle off)
                await self.engine.execute(
                    "DELETE FROM topic_votes WHERE id = ?", (existing["id"],)
                )
                return {"action": "removed", "vote_type": vote_type}
            else:
                # Change vote
                await self.engine.execute(
                    "UPDATE topic_votes SET vote_type = ?, created_at = ? WHERE id = ?",
                    (vote_type, now, existing["id"])
                )
                return {"action": "changed", "vote_type": vote_type}
        else:
            # New vote
            data = {
                "target_type": target_type,
                "target_id": target_id,
                "author_id": author_id,
                "vote_type": vote_type,
                "created_at": now,
            }
            await self.engine.put("topic_votes", 0, data)
            return {"action": "added", "vote_type": vote_type}

    async def get_topic_detail(
        self,
        topic_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Get topic detail with replies and vote counts"""
        topic = await self.engine.fetchone(
            """SELECT t.*,
                      COALESCE(u.nickname, u.display_name, u.username) as author_name,
                      u.avatar as author_avatar,
                      (SELECT COUNT(*) FROM topic_replies r WHERE r.topic_id = t.id) as reply_count,
                      (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'topic' AND v.target_id = t.id AND v.vote_type = 'upvote') as upvote_count,
                      (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'topic' AND v.target_id = t.id AND v.vote_type = 'downvote') as downvote_count
               FROM topic_discussions t
               LEFT JOIN users u ON t.author_id = u.id
               WHERE t.id = ?""",
            (topic_id,)
        )
        if not topic:
            return {"error": "话题不存在"}

        # Get replies with vote counts
        replies = await self.engine.fetchall(
            """SELECT r.*,
                      COALESCE(u.nickname, u.display_name, u.username) as author_name,
                      u.avatar as author_avatar,
                      (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'reply' AND v.target_id = r.id AND v.vote_type = 'upvote') as upvote_count,
                      (SELECT COUNT(*) FROM topic_votes v WHERE v.target_type = 'reply' AND v.target_id = r.id AND v.vote_type = 'downvote') as downvote_count
               FROM topic_replies r
               LEFT JOIN users u ON r.author_id = u.id
               WHERE r.topic_id = ?
               ORDER BY r.created_at ASC""",
            (topic_id,)
        )
        topic["replies"] = replies

        now = int(time.time())
        if topic["status"] == "open" and topic["deadline"] > now:
            topic["remaining_hours"] = round((topic["deadline"] - now) / 3600, 1)
        else:
            topic["remaining_hours"] = 0

        return topic

    async def close_topic(self, topic_id: int, author_id: int = None) -> Dict[str, Any]:
        """Close a topic (mark as closed)"""
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return {"error": "话题不存在"}
        if topic["status"] != "open":
            return {"error": "只能关闭进行中的话题"}

        now = int(time.time())
        await self.engine.execute(
            "UPDATE topic_discussions SET status = 'closed', updated_at = ? WHERE id = ?",
            (now, topic_id)
        )
        return {"id": topic_id, "status": "closed"}

    async def summarize_topic_mcp(
        self,
        topic_id: int,
        publish_blog: bool = True,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Summarize a closed topic using LLM and optionally publish as blog"""
        result = await self._do_summarize(topic_id, publish_blog)
        return result

    async def _do_summarize(self, topic_id: int, publish_blog: bool = True) -> Dict[str, Any]:
        """Internal: summarize a topic via LLM and optionally publish blog"""
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return {"error": "话题不存在"}
        if topic["status"] not in ("open", "closed"):
            return {"error": "只能总结进行中或已结束的话题"}

        # Get full topic detail
        detail = await self.get_topic_detail(topic_id)

        # Build summary prompt
        replies_text = ""
        for reply in detail.get("replies", []):
            author = reply.get("author_name", "匿名")
            replies_text += f"\n- {author}: {reply['content']}"
            if reply.get("upvote_count", 0) > 0:
                replies_text += f" (👍{reply['upvote_count']})"

        prompt = f"""请对以下讨论话题进行总结。

## 话题：{topic['title']}

### 话题描述：
{topic['description']}

### 讨论回复（共{detail.get('reply_count', 0)}条）：
{replies_text if replies_text else '暂无回复'}

### 投票统计：
👍 赞成: {detail.get('upvote_count', 0)}  👎 反对: {detail.get('downvote_count', 0)}

请生成一份结构化的总结，包含：
1. 讨论要点概述
2. 主要观点和分歧
3. 共识结论（如有）
4. 建议后续行动"""

        # Call LLM via llm_config plugin
        llm_plugin = self.ctx.get_plugin("llm_config")
        if not llm_plugin:
            return {"error": "LLM 配置插件未加载，无法生成总结"}

        llm_result = await llm_plugin.call_llm(
            prompt=prompt,
            system_prompt="你是一个专业的讨论总结助手。请用中文生成简洁、客观、结构化的讨论总结。"
        )

        if "error" in llm_result:
            return {"error": f"LLM 调用失败: {llm_result['error']}"}

        summary = llm_result.get("content", "")
        summary_post_id = None

        # Publish as blog post if requested
        if publish_blog:
            blog_plugin = self.ctx.get_plugin("blog")
            if blog_plugin:
                blog_result = await blog_plugin.create_post(
                    title=f"[讨论总结] {topic['title']}",
                    content=summary,
                    status="published",
                    tags=["讨论总结", topic['title'][:20]],
                    author_id=topic["author_id"]
                )
                if "id" in blog_result:
                    summary_post_id = blog_result["id"]

        # Update topic
        now = int(time.time())
        await self.engine.execute(
            "UPDATE topic_discussions SET status = 'summarized', summary = ?, summary_post_id = ?, updated_at = ? WHERE id = ?",
            (summary, summary_post_id, now, topic_id)
        )

        return {
            "id": topic_id,
            "status": "summarized",
            "summary": summary[:500],
            "summary_post_id": summary_post_id,
            "llm_model": llm_result.get("model", "unknown")
        }

    async def _mark_expired_topics(self) -> int:
        """Mark open topics past deadline as closed. Returns count of closed topics."""
        now = int(time.time())
        result = await self.engine.fetchall(
            "SELECT id FROM topic_discussions WHERE status = 'open' AND deadline < ?",
            (now,)
        )
        count = 0
        for row in result:
            await self.engine.execute(
                "UPDATE topic_discussions SET status = 'closed', updated_at = ? WHERE id = ?",
                (now, row["id"])
            )
            count += 1
        return count

    # ========================================================
    #  MCP call dispatcher
    # ========================================================

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        """MCP call dispatcher"""
        if tool_name == "create_topic":
            return await self.create_topic(mcp_token=mcp_token, **arguments)
        elif tool_name == "update_topic":
            return await self.update_topic(mcp_token=mcp_token, **arguments)
        elif tool_name == "list_topics":
            return await self.list_topics(**arguments)
        elif tool_name == "reply_topic":
            return await self.reply_topic(mcp_token=mcp_token, **arguments)
        elif tool_name == "vote":
            return await self.vote(mcp_token=mcp_token, **arguments)
        elif tool_name == "get_topic_detail":
            return await self.get_topic_detail(**arguments)
        elif tool_name == "summarize_topic":
            return await self.summarize_topic_mcp(mcp_token=mcp_token, **arguments)
        raise ValueError(f"Unknown tool: {tool_name}")

    # ========================================================
    #  HTTP page handlers
    # ========================================================

    async def topic_list_page(self, request, **kwargs):
        """Topic list page"""
        status_filter = request.query_params.get("status", "all")
        page = int(request.query_params.get("page", "1"))
        per_page = 20

        topics = await self.list_topics(
            status=status_filter,
            limit=per_page,
            offset=(page - 1) * per_page
        )

        # Count total
        conditions = []
        params = []
        if status_filter != "all":
            conditions.append("status = ?")
            params.append(status_filter)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_row = await self.engine.fetchone(
            f"SELECT COUNT(*) as cnt FROM topic_discussions {where_clause}",
            tuple(params)
        )
        total = count_row["cnt"] if count_row else 0
        total_pages = max(1, (total + per_page - 1) // per_page)

        pagination = {
            "current": page,
            "total": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

        current_user = await self.get_current_user(request)

        html = await self.ctx.template_engine.render("topic_list.html", {
            "nav_page": "topic",
            "topics": topics,
            "current_user": current_user,
            "status_filter": status_filter,
            "pagination": pagination,
        })
        return HTMLResponse(content=html)

    async def new_topic_page(self, request, **kwargs):
        """New topic page"""
        user = await self.get_current_user(request)
        if not user:
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/login", status_code=302)

        html = await self.ctx.template_engine.render("topic_detail.html", {
            "nav_page": "topic",
            "mode": "new",
            "current_user": user,
            "topic": {},
            "replies": [],
        })
        return HTMLResponse(content=html)

    async def edit_topic_page(self, request, **kwargs):
        """Edit topic page"""
        user = await self.get_current_user(request)
        if not user:
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/login", status_code=302)

        topic_id = int(kwargs.get("topic_id", 0))
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return self.error_html("话题不存在", 404)

        # Only author or admin can edit
        if topic["author_id"] != user["id"] and user.get("role") != "admin":
            return self.error_html("无权编辑此话题", 403)

        # Only allow editing open topics
        if topic["status"] != "open":
            return self.error_html("只能编辑进行中的话题", 400)

        now = int(time.time())
        remaining_hours = max(0, round((topic["deadline"] - now) / 3600, 1))

        html = await self.ctx.template_engine.render("topic_detail.html", {
            "nav_page": "topic",
            "mode": "edit",
            "current_user": user,
            "topic": dict(topic),
            "remaining_hours": remaining_hours,
            "replies": [],
        })
        return HTMLResponse(content=html)

    async def topic_detail_page(self, request, **kwargs):
        """Topic detail page"""
        topic_id = int(kwargs.get("topic_id", 0))
        detail = await self.get_topic_detail(topic_id)

        if "error" in detail:
            return self.error_html(detail["error"], 404)

        current_user = await self.get_current_user(request)

        # Get user's votes for this topic
        user_votes = {}
        if current_user:
            votes = await self.engine.fetchall(
                "SELECT target_type, target_id, vote_type FROM topic_votes WHERE author_id = ?",
                (current_user["id"],)
            )
            for v in votes:
                key = f"{v['target_type']}_{v['target_id']}"
                user_votes[key] = v["vote_type"]

        html = await self.ctx.template_engine.render("topic_detail.html", {
            "nav_page": "topic",
            "mode": "detail",
            "topic": detail,
            "replies": detail.get("replies", []),
            "current_user": current_user,
            "user_votes": user_votes,
        })
        return HTMLResponse(content=html)

    # ========================================================
    #  HTTP API handlers
    # ========================================================

    async def create_topic_api(self, request, **kwargs):
        """Create topic API"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        title = (body.get("title") or "").strip()
        description = (body.get("description") or "").strip()
        deadline_hours = int(body.get("deadline_hours", 72))

        if not title:
            return self.error_json("标题不能为空")

        result = await self.create_topic(
            title=title,
            description=description,
            deadline_hours=deadline_hours,
            author_id=user["id"]
        )
        return result

    async def update_topic_api(self, request, **kwargs):
        """Update topic API"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        topic_id = int(kwargs.get("topic_id", 0))
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        title = body.get("title")
        description = body.get("description")
        deadline_hours = body.get("deadline_hours")

        if deadline_hours is not None:
            deadline_hours = int(deadline_hours)

        result = await self.update_topic(
            topic_id=topic_id,
            title=title,
            description=description,
            deadline_hours=deadline_hours,
            author_id=user["id"]
        )
        return result

    async def reply_topic_api(self, request, **kwargs):
        """Reply topic API"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        topic_id = int(kwargs.get("topic_id", 0))
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        content = (body.get("content") or "").strip()
        parent_id = body.get("parent_id")

        if not content:
            return self.error_json("回复内容不能为空")

        return await self.reply_topic(
            topic_id=topic_id,
            content=content,
            parent_id=parent_id,
            author_id=user["id"]
        )

    async def vote_api(self, request, **kwargs):
        """Vote API"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        topic_id = int(kwargs.get("topic_id", 0))
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        target_type = body.get("target_type", "topic")
        target_id = int(body.get("target_id", topic_id))
        vote_type = body.get("vote_type", "upvote")

        if vote_type not in ("upvote", "downvote"):
            return self.error_json("无效的投票类型")

        return await self.vote(
            target_type=target_type,
            target_id=target_id,
            vote_type=vote_type,
            author_id=user["id"]
        )

    async def close_topic_api(self, request, **kwargs):
        """Close topic API"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        topic_id = int(kwargs.get("topic_id", 0))
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return self.error_json("话题不存在", 404)

        # Only author or admin can close
        if topic["author_id"] != user["id"] and user.get("role") != "admin":
            return self.error_json("无权关闭此话题", 403)

        return await self.close_topic(topic_id)

    async def summarize_topic_api(self, request, **kwargs):
        """Summarize topic API (trigger AI summarization)"""
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        topic_id = int(kwargs.get("topic_id", 0))
        topic = await self.engine.fetchone(
            "SELECT * FROM topic_discussions WHERE id = ?", (topic_id,)
        )
        if not topic:
            return self.error_json("话题不存在", 404)

        # Only author or admin can trigger summarize
        if topic["author_id"] != user["id"] and user.get("role") != "admin":
            return self.error_json("无权总结此话题", 403)

        # Close topic first if still open
        if topic["status"] == "open":
            await self.close_topic(topic_id)

        result = await self._do_summarize(topic_id, publish_blog=True)

        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def check_expired_api(self, request, **kwargs):
        """Check and close expired topics (can be called by cron)"""
        user = await self.get_current_user(request)
        if not user or user.get("role") != "admin":
            return self.error_json("仅管理员可执行", 403)

        count = await self._mark_expired_topics()
        return {"closed_count": count}
