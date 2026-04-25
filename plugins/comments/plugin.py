"""Comments plugin - unified comment system for blog/microblog/notes

Supports:
- Nested replies (one level of nesting)
- Author review (approve/reject)
- Notification system
- No guest comments (login required)
"""
import time
from typing import List, Dict, Any, Optional

from app.plugin import Plugin, PluginContext, Route
from app.log import get_logger

log = get_logger(__name__, "comments")

VALID_TARGET_TYPES = {"blog", "microblog", "note"}
VALID_STATUSES = {"pending", "approved", "rejected"}

# Maps target_type → table name for author lookups
TARGET_TABLE_MAP = {
    "blog": "blog_posts",
    "microblog": "microblog_posts",
    "note": "notes",
}


class CommentsPlugin(Plugin):
    """Comments plugin"""

    @property
    def name(self) -> str:
        return "comments"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.config = ctx.config
        self._ctx = ctx
        log.info("Comments plugin initialized")

    # ------------------------------------------------------------------
    #  Routes
    # ------------------------------------------------------------------

    def routes(self) -> List[Route]:
        return [
            Route("/api/comments", "GET", self.list_comments, "comments.list"),
            Route("/api/comments", "POST", self.create_comment, "comments.create"),
            Route("/api/comments/{comment_id}/review", "POST", self.review_comment, "comments.review"),
            Route("/api/comments/{comment_id}", "DELETE", self.delete_comment, "comments.delete"),
            Route("/api/comments/pending", "GET", self.list_pending_comments, "comments.pending"),
            # Notifications
            Route("/api/notifications", "GET", self.list_notifications, "notifications.list"),
            Route("/api/notifications/{notification_id}/read", "POST", self.mark_notification_read, "notifications.read"),
            Route("/api/notifications/read-all", "POST", self.mark_all_notifications_read, "notifications.read_all"),
            Route("/api/notifications/{notif_id}/validate", "GET", self.validate_notification, "notifications.validate"),
            Route("/api/notifications/unread-count", "GET", self.unread_count, "notifications.unread_count"),
            # Pages
            Route("/comments/notifications", "GET", self.notifications_page, "notifications.page"),
            Route("/comments/notifications/read", "POST", self.mark_all_and_redirect, "notifications.read_all_page"),
        ]

    # ------------------------------------------------------------------
    #  Comment CRUD
    # ------------------------------------------------------------------

    async def list_comments(self, request, **kwargs) -> Any:
        """GET /api/comments?target_type=blog&target_id=5

        Returns approved comments with nested replies.
        If user is logged in, also includes their own pending comments.
        """
        from starlette.responses import JSONResponse

        target_type = request.query_params.get("target_type", request.query_params.get("target", ""))
        target_id = request.query_params.get("target_id", "")

        if not target_type or not target_id:
            return self.error_json("缺少 target 或 target_id 参数")

        if target_type not in VALID_TARGET_TYPES:
            return self.error_json(f"无效的 target_type: {target_type}")

        try:
            target_id = int(target_id)
        except ValueError:
            return self.error_json("target_id 必须为整数")

        # Get current user (optional — used to show own pending comments)
        current_user = await self.get_current_user(request)
        current_user_id = current_user["id"] if current_user else None

        # Fetch top-level comments (approved + own pending if logged in)
        if current_user_id:
            rows = await self.engine.fetchall(
                """SELECT c.*, u.username as author_name, u.avatar as author_avatar
                   FROM comments c
                   LEFT JOIN users u ON c.author_id = u.id
                   WHERE c.target_type = ? AND c.target_id = ? AND c.parent_id IS NULL
                     AND (c.status = 'approved' OR c.author_id = ?)
                   ORDER BY c.created_at ASC""",
                (target_type, target_id, current_user_id)
            )
        else:
            rows = await self.engine.fetchall(
                """SELECT c.*, u.username as author_name, u.avatar as author_avatar
                   FROM comments c
                   LEFT JOIN users u ON c.author_id = u.id
                   WHERE c.target_type = ? AND c.target_id = ? AND c.parent_id IS NULL
                     AND c.status = 'approved'
                   ORDER BY c.created_at ASC""",
                (target_type, target_id)
            )

        # Build nested structure
        # Determine if current user is the content author (can review comments)
        is_content_author = False
        if current_user_id:
            target = await self.engine.get(TARGET_TABLE_MAP.get(target_type, ""), target_id)
            if target and target.get("author_id") == current_user_id:
                is_content_author = True

        # Batch-fetch all replies for this target in one query (avoid N+1)
        top_ids = [r["id"] for r in rows]
        if top_ids:
            placeholders = ",".join("?" * len(top_ids))
            if current_user_id:
                all_replies = await self.engine.fetchall(
                    f"""SELECT c.*, u.username as author_name, u.avatar as author_avatar
                       FROM comments c
                       LEFT JOIN users u ON c.author_id = u.id
                       WHERE c.parent_id IN ({placeholders})
                         AND (c.status = 'approved' OR c.author_id = ?)
                       ORDER BY c.created_at ASC""",
                    (*top_ids, current_user_id)
                )
            else:
                all_replies = await self.engine.fetchall(
                    f"""SELECT c.*, u.username as author_name, u.avatar as author_avatar
                       FROM comments c
                       LEFT JOIN users u ON c.author_id = u.id
                       WHERE c.parent_id IN ({placeholders}) AND c.status = 'approved'
                       ORDER BY c.created_at ASC""",
                    top_ids
                )
            # Group replies by parent_id
            reply_map: dict = {}
            for r in all_replies:
                reply_map.setdefault(r["parent_id"], []).append(dict(r))
        else:
            reply_map = {}

        comments = []
        for row in rows:
            comment = dict(row)
            comment["replies"] = reply_map.get(comment["id"], [])
            # Only content author can review, not comment author
            comment["can_review"] = is_content_author
            for reply in comment["replies"]:
                reply["can_review"] = is_content_author
            comments.append(comment)

        return JSONResponse({"comments": comments, "total": len(comments), "can_review": is_content_author})

    async def create_comment(self, request, **kwargs) -> Any:
        """POST /api/comments

        Create a new comment or reply. Requires login.
        New comments default to status='pending'.
        """
        from starlette.responses import JSONResponse

        # Must be logged in
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        try:
            data = await request.json()
        except Exception:
            return self.error_json("无效的请求体")

        target_type = data.get("target_type", "")
        target_id = data.get("target_id")
        parent_id = data.get("parent_id")
        content = data.get("content", "").strip()

        # Validate
        if target_type not in VALID_TARGET_TYPES:
            return self.error_json(f"无效的 target_type: {target_type}")

        if not target_id:
            return self.error_json("缺少 target_id")

        if not content:
            return self.error_json("评论内容不能为空")

        if len(content) > 2000:
            return self.error_json("评论内容不能超过 2000 字")

        # Verify target exists
        table = TARGET_TABLE_MAP.get(target_type)
        if table:
            target = await self.engine.get(table, int(target_id))
            if not target:
                return self.error_json("评论目标不存在")

        # Validate parent_id
        if parent_id is not None:
            parent = await self.engine.get("comments", int(parent_id))
            if not parent:
                return self.error_json("父评论不存在")
            if parent["target_type"] != target_type or parent["target_id"] != int(target_id):
                return self.error_json("父评论不属于同一内容")
            # Only allow one level of nesting: parent must be top-level
            if parent.get("parent_id"):
                return self.error_json("不支持多层嵌套回复，请回复顶级评论")

        # Self-comment on own content → auto-approve
        target_author_id = target.get("author_id") if target else None
        user_id = user["id"]
        is_content_author = bool(target and target_author_id == user_id)
        initial_status = "approved" if is_content_author else "pending"

        # Create comment
        now = int(time.time())
        comment_data = {
            "target_type": target_type,
            "target_id": int(target_id),
            "parent_id": parent_id,
            "author_id": user["id"],
            "content": content,
            "status": initial_status,
            "reviewer_id": user["id"] if is_content_author else None,
            "reviewed_at": now if is_content_author else None,
            "created_at": now,
            "updated_at": now,
        }
        comment_id = await self.engine.put("comments", 0, comment_data)

        # Send notification to content author
        if target:
            content_author_id = target.get("author_id")
            if content_author_id and content_author_id != user["id"]:
                notif_type = "reply_pending" if parent_id else "comment_pending"
                await self._create_notification(
                    user_id=content_author_id,
                    notif_type=notif_type,
                    target_type=target_type,
                    target_id=int(target_id),
                    comment_id=comment_id,
                    content=content[:50],
                )

        # If replying, also notify the parent comment author
        if parent_id and parent:
            parent_author_id = parent.get("author_id")
            if parent_author_id and parent_author_id != user["id"]:
                try:
                    await self._create_notification(
                        user_id=parent_author_id,
                        notif_type="reply_pending",
                        target_type=target_type,
                        target_id=int(target_id),
                        comment_id=comment_id,
                        content=content[:50],
                    )
                except Exception as e:
                    log.error(f"create_comment: parent notification failed: {e}")
                    raise

        log.info(f"Comment created: id={comment_id}, target={target_type}/{target_id}, author={user['id']}")
        return JSONResponse({
            "id": comment_id,
            "status": "pending",
            "message": "评论已提交，等待作者审核"
        }, status_code=201)

    async def review_comment(self, request, **kwargs) -> Any:
        """POST /api/comments/{comment_id}/review

        Approve or reject a comment. Only the content author can review.
        """
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        comment_id = int(request.path_params["comment_id"])
        comment = await self.engine.get("comments", comment_id)
        if not comment:
            return self.error_json("评论不存在", 404)

        try:
            data = await request.json()
        except Exception:
            return self.error_json("无效的请求体")

        action = data.get("action", "")
        if action not in ("approve", "reject"):
            return self.error_json("action 必须为 approve 或 reject")

        # Only the content author can review
        table = TARGET_TABLE_MAP.get(comment["target_type"])
        if not table:
            return self.error_json("无效的评论目标类型")

        target = await self.engine.get(table, comment["target_id"])
        if not target:
            return self.error_json("评论目标不存在")

        if target.get("author_id") != user["id"] and user.get("role") != "admin":
            return self.error_json("只有内容作者可以审核评论", 403)

        # Already reviewed?
        if comment["status"] != "pending":
            return self.error_json(f"评论已审核，当前状态: {comment['status']}")

        # Update
        now = int(time.time())
        new_status = "approved" if action == "approve" else "rejected"
        await self.engine.put("comments", comment_id, {
            **comment,
            "status": new_status,
            "reviewer_id": user["id"],
            "reviewed_at": now,
            "updated_at": now,
        })

        # Notify the comment author
        notif_type = "comment_approved" if action == "approve" else "comment_rejected"
        if comment["author_id"] != user["id"]:
            await self._create_notification(
                user_id=comment["author_id"],
                notif_type=notif_type,
                target_type=comment["target_type"],
                target_id=comment["target_id"],
                comment_id=comment_id,
                content=comment["content"][:50],
            )

        log.info(f"Comment {comment_id} reviewed: {new_status} by user {user['id']}")
        return JSONResponse({
            "id": comment_id,
            "status": new_status,
            "message": "已审核通过" if action == "approve" else "已拒绝"
        })

    async def delete_comment(self, request, **kwargs) -> Any:
        """DELETE /api/comments/{comment_id}

        Delete a comment. Only the comment author or the content author can delete.
        Deleting a top-level comment also deletes all replies.
        """
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        comment_id = int(request.path_params["comment_id"])
        comment = await self.engine.get("comments", comment_id)
        if not comment:
            return self.error_json("评论不存在", 404)

        # Check permission: comment author OR content author OR admin
        is_comment_author = comment["author_id"] == user["id"]
        is_content_author = False

        table = TARGET_TABLE_MAP.get(comment["target_type"])
        if table:
            target = await self.engine.get(table, comment["target_id"])
            if target and target.get("author_id") == user["id"]:
                is_content_author = True

        is_admin = user.get("role") == "admin"

        if not (is_comment_author or is_content_author or is_admin):
            return self.error_json("无权删除此评论", 403)

        # Delete child replies first
        replies = await self.engine.fetchall(
            "SELECT id FROM comments WHERE parent_id = ?",
            (comment_id,)
        )
        for reply in replies:
            await self.engine.delete("comments", reply["id"])

        # Delete the comment itself
        await self.engine.delete("comments", comment_id)

        log.info(f"Comment {comment_id} deleted by user {user['id']}")
        return JSONResponse({"success": True})

    async def list_pending_comments(self, request, **kwargs) -> Any:
        """GET /api/comments/pending?target_type=blog&target_id=5

        List pending and rejected comments for the content author.
        """
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        target_type = request.query_params.get("target_type", request.query_params.get("target", ""))
        target_id = request.query_params.get("target_id", "")

        if not target_type or not target_id:
            return self.error_json("缺少 target 或 target_id 参数")

        if target_type not in VALID_TARGET_TYPES:
            return self.error_json(f"无效的 target_type: {target_type}")

        try:
            target_id = int(target_id)
        except ValueError:
            return self.error_json("target_id 必须为整数")

        # Verify the user is the content author
        table = TARGET_TABLE_MAP.get(target_type)
        if not table:
            return self.error_json("无效的目标类型")

        target = await self.engine.get(table, target_id)
        if not target:
            return self.error_json("内容不存在")

        if target.get("author_id") != user["id"] and user.get("role") != "admin":
            return self.error_json("只有内容作者可以查看待审评论", 403)

        rows = await self.engine.fetchall(
            """SELECT c.*, u.username as author_name, u.avatar as author_avatar
               FROM comments c
               LEFT JOIN users u ON c.author_id = u.id
               WHERE c.target_type = ? AND c.target_id = ?
                 AND c.status IN ('pending', 'rejected')
               ORDER BY c.created_at ASC""",
            (target_type, target_id)
        )
        comments = [dict(r) for r in rows]
        for c in comments:
            c["can_review"] = True  # content author can review
        return JSONResponse({"comments": comments, "total": len(comments)})

    # ------------------------------------------------------------------
    #  Notifications
    # ------------------------------------------------------------------

    async def list_notifications(self, request, **kwargs) -> Any:
        """GET /api/notifications?page=1&limit=20"""
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        page = int(request.query_params.get("page", "1"))
        limit = min(int(request.query_params.get("limit", "20")), 100)
        offset = (page - 1) * limit

        rows = await self.engine.fetchall(
            """SELECT * FROM notifications
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (user["id"], limit, offset)
        )

        # Get total count
        total_row = await self.engine.fetchone(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ?",
            (user["id"],)
        )
        total = total_row["cnt"] if total_row else 0

        return JSONResponse({
            "notifications": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        })

    async def mark_notification_read(self, request, **kwargs) -> Any:
        """POST /api/notifications/{notification_id}/read"""
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        notification_id = int(request.path_params["notification_id"])
        notif = await self.engine.get("notifications", notification_id)
        if not notif:
            return self.error_json("通知不存在", 404)

        if notif["user_id"] != user["id"]:
            return self.error_json("无权操作", 403)

        await self.engine.put("notifications", notification_id, {
            **notif,
            "is_read": 1,
        })

        return JSONResponse({"success": True})

    async def mark_all_notifications_read(self, request, **kwargs) -> Any:
        """POST /api/notifications/read-all"""
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        await self.engine.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
            (user["id"],)
        )

        return JSONResponse({"success": True})

    async def unread_count(self, request, **kwargs) -> Any:
        """GET /api/notifications/unread-count"""
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        row = await self.engine.fetchone(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],)
        )

        return JSONResponse({"count": row["cnt"] if row else 0})

    # ------------------------------------------------------------------
    #  Page routes
    # ------------------------------------------------------------------

    async def notifications_page(self, request, **kwargs) -> Any:
        """GET /comments/notifications - Notifications page"""
        from starlette.responses import HTMLResponse

        user = await self.get_current_user(request)
        if not user:
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/login", status_code=302)

        rows = await self.engine.fetchall(
            """SELECT * FROM notifications
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT 50""",
            (user["id"],)
        )

        # Build display-friendly messages
        notifications = []
        for row in rows:
            n = dict(row)
            # Map notification type to display type
            ntype = n.get("type", "system")
            if "comment" in ntype:
                n["type"] = "comment"
            elif "reply" in ntype:
                n["type"] = "reply"
            elif "approved" in ntype:
                n["type"] = "approved"
            elif "rejected" in ntype:
                n["type"] = "rejected"
            else:
                n["type"] = "system"

            # Keep created_at as int timestamp for datefmt filter
            # Build human-readable message
            content_preview = n.get("content", "")
            target_type = n.get("target_type", "")
            target_type_cn = {"blog": "博客", "microblog": "微博", "note": "笔记"}.get(target_type, target_type)
            if ntype == "comment_pending":
                n["message"] = f"有人评论了你的{target_type_cn}：{content_preview}..."
            elif ntype == "reply_pending":
                n["message"] = f"有人回复了你的评论：{content_preview}..."
            elif ntype == "comment_approved":
                n["message"] = f"你的评论已通过审核"
            elif ntype == "comment_rejected":
                n["message"] = f"你的评论未通过审核"
            else:
                n["message"] = content_preview or "系统通知"

            notifications.append(n)

        html = await self._ctx.template_engine.render("notifications.html", {
            "notifications": notifications,
            "nav_page": "notifications",
        })
        return HTMLResponse(content=html)

    async def validate_notification(self, request, notif_id: int, **kwargs) -> Any:
        """GET /api/notifications/{notif_id}/validate

        验证通知指向的内容是否仍存在。
        - 目标存在：返回 {"exists": true, "target_url": "..."}
        - 目标不存在：删除通知，返回 {"exists": false, "notif_id": ...}
        """
        from starlette.responses import JSONResponse

        user = await self.get_current_user(request)
        if not user:
            return self.error_json("请先登录", 401)

        row = await self.engine.fetchone(
            "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
            (notif_id, user["id"])
        )
        if not row:
            return JSONResponse({"exists": False, "notif_id": notif_id})

        notif = dict(row)
        target_url = notif.get("target_url", "") or ""

        # 没有 target_url 或为 #，视为有效但无跳转
        if not target_url or target_url == "#":
            return JSONResponse({"exists": True, "target_url": "#"})

        # 解析 target_url 判断目标类型和 ID
        target_type = notif.get("target_type", "")
        target_id = notif.get("target_id", 0)
        exists = False

        if target_type == "blog":
            row2 = await self.engine.fetchone("SELECT id FROM blog_posts WHERE id = ?", (target_id,))
            exists = row2 is not None
        elif target_type == "microblog":
            row2 = await self.engine.fetchone("SELECT id FROM microblog_posts WHERE id = ?", (target_id,))
            exists = row2 is not None
        elif target_type == "note":
            row2 = await self.engine.fetchone("SELECT id FROM notes WHERE id = ?", (target_id,))
            exists = row2 is not None

        if not exists:
            # 目标已被删除，清理通知
            await self.engine.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
            return JSONResponse({"exists": False, "notif_id": notif_id})

        return JSONResponse({"exists": True, "target_url": target_url})

    async def mark_all_and_redirect(self, request, **kwargs) -> Any:
        """POST /comments/notifications/read - Mark all read and redirect"""
        user = await self.get_current_user(request)
        if user:
            await self.engine.execute(
                "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
                (user["id"],)
            )
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/comments/notifications", status_code=302)

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    async def _create_notification(
        self,
        user_id: int,
        notif_type: str,
        target_type: str,
        target_id: int,
        comment_id: int,
        content: str,
    ) -> int:
        """Create a notification record"""
        # Compute target URL for quick navigation
        if target_type == "blog":
            target_url = f"/blog/view/{target_id}"
        elif target_type == "microblog":
            target_url = f"/microblog#post-{target_id}"
        elif target_type == "note":
            target_url = f"/notes/{target_id}"
        else:
            target_url = f"/{target_type}/view/{target_id}"

        now = int(time.time())
        notif_id = await self.engine.put("notifications", 0, {
            "user_id": user_id,
            "type": notif_type,
            "target_type": target_type,
            "target_id": target_id,
            "comment_id": comment_id,
            "content": content,
            "is_read": 0,
            "created_at": now,
            "updated_at": now,
            "target_url": target_url,
        })
        return notif_id

    # ------------------------------------------------------------------
    #  MCP tools (for AI agent access)
    # ------------------------------------------------------------------

    def mcp_tools(self):
        from app.plugin import MCPTool
        return [
            MCPTool(
                name="list_comments",
                description="List comments for a blog/microblog/note post",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_type": {"type": "string", "enum": ["blog", "microblog", "note"]},
                        "target_id": {"type": "integer"},
                    },
                    "required": ["target_type", "target_id"],
                },
                handler=self._mcp_list_comments,
            ),
        ]

    async def _mcp_list_comments(self, target_type: str, target_id: int) -> Dict:
        """MCP tool: list approved comments"""
        rows = await self.engine.fetchall(
            """SELECT c.*, u.username as author_name
               FROM comments c
               LEFT JOIN users u ON c.author_id = u.id
               WHERE c.target_type = ? AND c.target_id = ? AND c.status = 'approved'
               ORDER BY c.created_at ASC""",
            (target_type, target_id)
        )
        return {"comments": [dict(r) for r in rows]}
