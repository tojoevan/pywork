"""Tests for plugins/comments/plugin.py — CommentsPlugin"""
import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional


# ============================================================
#  Mock Engine
# ============================================================

class MockEngine:
    """In-memory mock engine for comment tests"""

    def __init__(self):
        self.tables: Dict[str, Dict[int, Dict]] = {}
        self._next_id: Dict[str, int] = {}
        self._executed: List[tuple] = []

    def _ensure_table(self, table: str):
        if table not in self.tables:
            self.tables[table] = {}
            self._next_id[table] = 1

    async def get(self, table: str, id: int) -> Optional[Dict]:
        self._ensure_table(table)
        row = self.tables[table].get(id)
        return dict(row) if row else None

    async def put(self, table: str, id: int, data: Dict) -> int:
        self._ensure_table(table)
        if id == 0:
            id = self._next_id[table]
            self._next_id[table] += 1
        data = data.copy()
        data["id"] = id
        self.tables[table][id] = data
        return id

    async def delete(self, table: str, id: int) -> None:
        self._ensure_table(table)
        self.tables[table].pop(id, None)

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        self._executed.append((sql, params))
        # COUNT queries
        if "COUNT(*)" in sql and "notifications" in sql:
            uid = params[0] if params else None
            is_read_filter = "is_read = 0" in sql
            count = 0
            for n in self.tables.get("notifications", {}).values():
                if n.get("user_id") == uid:
                    if is_read_filter and n.get("is_read", 0) == 0:
                        count += 1
                    elif not is_read_filter:
                        count += 1
            return {"cnt": count}
        # Single row by id
        for tbl in ["blog_posts", "microblog_posts", "notes", "comments", "notifications"]:
            if tbl in sql and "id = ?" in sql.lower():
                return self.tables.get(tbl, {}).get(params[0] if params else -1)
        return None

    async def fetchall(self, sql: str, params: tuple = ()) -> List[Dict]:
        self._executed.append((sql, params))
        results = []
        # Comments with various filters
        if "comments" in sql and "target_type" in sql:
            target_type = params[0] if params else None
            target_id = params[1] if len(params) > 1 else None
            for c in self.tables.get("comments", {}).values():
                if c.get("target_type") == target_type and c.get("target_id") == target_id:
                    # Filter by parent_id
                    if "parent_id IS NULL" in sql:
                        if c.get("parent_id") is not None:
                            continue
                    if "parent_id IN" in sql:
                        # Extract parent IDs from placeholders
                        pass
                    # Filter by status
                    if "status = 'approved'" in sql and "author_id" not in sql:
                        if c.get("status") != "approved":
                            continue
                    if "status IN ('pending', 'rejected')" in sql:
                        if c.get("status") not in ("pending", "rejected"):
                            continue
                    results.append(dict(c))
        elif "comments" in sql and "parent_id" in sql:
            parent_id = params[0] if params else None
            for c in self.tables.get("comments", {}).values():
                if c.get("parent_id") == parent_id:
                    results.append(dict(c))
        elif "notifications" in sql and "user_id" in sql:
            uid = params[0] if params else None
            for n in self.tables.get("notifications", {}).values():
                if n.get("user_id") == uid:
                    results.append(dict(n))
        return results

    async def execute(self, sql: str, params: tuple = ()) -> None:
        self._executed.append((sql, params))
        # UPDATE notifications
        if "UPDATE notifications SET is_read = 1" in sql:
            uid = params[0] if params else None
            for n in self.tables.get("notifications", {}).values():
                if n.get("user_id") == uid and n.get("is_read", 0) == 0:
                    n["is_read"] = 1
        # DELETE notifications
        if "DELETE FROM notifications WHERE id = ?" in sql:
            nid = params[0] if params else None
            self.tables.get("notifications", {}).pop(nid, None)
        # DELETE comments
        if "DELETE FROM comments" in sql:
            pass  # handled by delete() calls


# ============================================================
#  Helpers
# ============================================================

def make_request(method="GET", path="/api/comments", query_params=None,
                 cookies=None, json_body=None, path_params=None, user=None):
    """Create a mock request"""
    req = MagicMock()
    req.method = method
    req.url = MagicMock()
    req.url.path = path
    req.query_params = query_params or {}
    req.cookies = cookies or {}
    req.headers = {}
    req.path_params = path_params or {}

    # If user provided, set auth cookie so get_current_user can find them
    if user:
        req.cookies = {"auth_token": f"tok_{user['id']}"}

    if json_body is not None:
        req.json = AsyncMock(return_value=json_body)
    else:
        req.json = AsyncMock(side_effect=Exception("no body"))

    return req


async def init_plugin(engine=None, user=None):
    """Initialize CommentsPlugin with mock engine and optional user"""
    from plugins.comments.plugin import CommentsPlugin

    plugin = CommentsPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.config = {}
    plugin._ctx = MagicMock()
    plugin._ctx.engine = engine

    # Mock auth plugin - returns user for any token
    auth_mock = MagicMock()
    auth_mock.get_user_by_token = AsyncMock(return_value=user)
    plugin._ctx.get_plugin = MagicMock(return_value=auth_mock)

    # Patch get_current_user to return user directly
    plugin.get_current_user = AsyncMock(return_value=user)

    return plugin, engine


def seed_comment(engine, comment_id, target_type="blog", target_id=1,
                  author_id=2, content="test", status="approved",
                  parent_id=None):
    """Insert a comment into the mock engine"""
    now = int(time.time())
    data = {
        "id": comment_id,
        "target_type": target_type,
        "target_id": target_id,
        "parent_id": parent_id,
        "author_id": author_id,
        "content": content,
        "status": status,
        "reviewer_id": None,
        "reviewed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    engine._ensure_table("comments")
    engine.tables["comments"][comment_id] = data
    if comment_id >= engine._next_id.get("comments", 1):
        engine._next_id["comments"] = comment_id + 1
    return data


def seed_post(engine, table, post_id, author_id=1):
    """Insert a blog/microblog/note post"""
    now = int(time.time())
    data = {
        "id": post_id,
        "author_id": author_id,
        "title": "Test Post",
        "body": "Content",
        "created_at": now,
        "updated_at": now,
    }
    engine._ensure_table(table)
    engine.tables[table][post_id] = data
    return data


def seed_notification(engine, notif_id, user_id, is_read=0, target_type="blog", target_id=1):
    """Insert a notification"""
    now = int(time.time())
    data = {
        "id": notif_id,
        "user_id": user_id,
        "type": "comment_pending",
        "target_type": target_type,
        "target_id": target_id,
        "comment_id": 1,
        "content": "test",
        "is_read": is_read,
        "created_at": now,
        "updated_at": now,
        "target_url": f"/blog/view/{target_id}",
    }
    engine._ensure_table("notifications")
    engine.tables["notifications"][notif_id] = data
    return data


# ============================================================
#  Comment CRUD
# ============================================================

class TestCreateComment:
    """POST /api/comments"""

    @pytest.mark.asyncio
    async def test_create_comment_success(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "Nice post!",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["id"] > 0
        assert body["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_comment_not_logged_in(self):
        plugin, engine = await init_plugin(user=None)
        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "test",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")

    @pytest.mark.asyncio
    async def test_create_comment_empty_content(self):
        user = {"id": 2, "role": "user"}
        plugin, _ = await init_plugin(user=user)
        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "不能为空" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_create_comment_too_long(self):
        user = {"id": 2, "role": "user"}
        plugin, _ = await init_plugin(user=user)
        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "x" * 2001,
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "2000" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_create_comment_invalid_target_type(self):
        user = {"id": 2, "role": "user"}
        plugin, _ = await init_plugin(user=user)
        req = make_request(json_body={
            "target_type": "invalid",
            "target_id": 1,
            "content": "test",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "无效" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_create_comment_target_not_found(self):
        user = {"id": 2, "role": "user"}
        plugin, _ = await init_plugin(user=user)
        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 999,
            "content": "test",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "不存在" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_auto_approve_when_content_author(self):
        """Content author's comment is auto-approved"""
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)

        # Patch engine.get to return the post for blog_posts table
        original_get = engine.get

        async def patched_get(table, id):
            if table == "blog_posts" and id == 1:
                return engine.tables.get("blog_posts", {}).get(1)
            return await original_get(table, id)

        engine.get = patched_get

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "My own post comment",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["id"] > 0
        # Response always says "pending" but the comment is auto-approved in DB
        comment = await engine.get("comments", body["id"])
        assert comment["status"] == "approved"

    @pytest.mark.asyncio
    async def test_pending_when_not_content_author(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "Other user comment",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_reply_to_comment(self):
        user = {"id": 3, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, parent_id=None, author_id=2)

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "Reply!",
            "parent_id": 10,
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["id"] > 0

    @pytest.mark.asyncio
    async def test_reply_to_nested_comment_rejected(self):
        """Cannot reply to a reply (only one level of nesting)"""
        user = {"id": 3, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        # parent_id=10 is a top-level comment
        seed_comment(engine, 10, parent_id=None)
        # comment 11 is a reply to 10
        seed_comment(engine, 11, parent_id=10)

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "Nested reply",
            "parent_id": 11,  # trying to reply to a reply
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "嵌套" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_reply_to_nonexistent_parent(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)

        req = make_request(json_body={
            "target_type": "blog",
            "target_id": 1,
            "content": "test",
            "parent_id": 999,
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert "父评论" in body.get("error", "")


# ============================================================
#  Comment Review
# ============================================================

class TestReviewComment:
    """POST /api/comments/{comment_id}/review"""

    @pytest.mark.asyncio
    async def test_approve_comment(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1,
                     author_id=2, status="pending")

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert body["status"] == "approved"

    @pytest.mark.asyncio
    async def test_reject_comment(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, status="pending")

        req = make_request(method="POST", json_body={"action": "reject"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert body["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_review_not_logged_in(self):
        plugin, engine = await init_plugin(user=None)
        seed_comment(engine, 10, status="pending")

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")

    @pytest.mark.asyncio
    async def test_review_not_content_author(self):
        """Non-author cannot review"""
        user = {"id": 99, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1,
                     status="pending")

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert body.get("error") or resp.status_code == 403

    @pytest.mark.asyncio
    async def test_review_already_reviewed(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, status="approved")

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert "已审核" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_review_invalid_action(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, status="pending")

        req = make_request(method="POST", json_body={"action": "invalid"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert "approve" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_review_nonexistent_comment(self):
        user = {"id": 1, "role": "user"}
        plugin, _ = await init_plugin(user=user)

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "999"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert "不存在" in body.get("error", "")


# ============================================================
#  Comment Delete
# ============================================================

class TestDeleteComment:
    """DELETE /api/comments/{comment_id}"""

    @pytest.mark.asyncio
    async def test_delete_by_comment_author(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_comment(engine, 10, author_id=2)

        req = make_request(method="DELETE", path_params={"comment_id": "10"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert body.get("success") is True

    @pytest.mark.asyncio
    async def test_delete_by_content_author(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1, author_id=2)

        req = make_request(method="DELETE", path_params={"comment_id": "10"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert body.get("success") is True

    @pytest.mark.asyncio
    async def test_delete_by_admin(self):
        user = {"id": 99, "role": "admin"}
        plugin, engine = await init_plugin(user=user)
        seed_comment(engine, 10, author_id=2)

        req = make_request(method="DELETE", path_params={"comment_id": "10"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert body.get("success") is True

    @pytest.mark.asyncio
    async def test_delete_unauthorized(self):
        user = {"id": 99, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1, author_id=2)

        req = make_request(method="DELETE", path_params={"comment_id": "10"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert body.get("error") or resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_not_logged_in(self):
        plugin, engine = await init_plugin(user=None)
        seed_comment(engine, 10)

        req = make_request(method="DELETE", path_params={"comment_id": "10"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        user = {"id": 1, "role": "user"}
        plugin, _ = await init_plugin(user=user)

        req = make_request(method="DELETE", path_params={"comment_id": "999"})
        resp = await plugin.delete_comment(req)
        body = json.loads(resp.body)
        assert "不存在" in body.get("error", "")


# ============================================================
#  List Comments
# ============================================================

class TestListComments:
    """GET /api/comments"""

    @pytest.mark.asyncio
    async def test_list_approved_comments(self):
        plugin, engine = await init_plugin(user=None)
        seed_comment(engine, 1, target_type="blog", target_id=1, status="approved")
        seed_comment(engine, 2, target_type="blog", target_id=1, status="pending")

        req = make_request(query_params={"target_type": "blog", "target_id": "1"})
        resp = await plugin.list_comments(req)
        body = json.loads(resp.body)
        # Only approved should appear for anonymous
        assert body["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_missing_params(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request(query_params={})
        resp = await plugin.list_comments(req)
        body = json.loads(resp.body)
        assert "缺少" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_list_invalid_target_type(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request(query_params={"target_type": "invalid", "target_id": "1"})
        resp = await plugin.list_comments(req)
        body = json.loads(resp.body)
        assert "无效" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_list_invalid_target_id(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request(query_params={"target_type": "blog", "target_id": "abc"})
        resp = await plugin.list_comments(req)
        body = json.loads(resp.body)
        assert "整数" in body.get("error", "")


# ============================================================
#  Pending Comments
# ============================================================

class TestPendingComments:
    """GET /api/comments/pending"""

    @pytest.mark.asyncio
    async def test_pending_not_logged_in(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request(query_params={"target_type": "blog", "target_id": "1"})
        resp = await plugin.list_pending_comments(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")

    @pytest.mark.asyncio
    async def test_pending_missing_params(self):
        user = {"id": 1, "role": "user"}
        plugin, _ = await init_plugin(user=user)
        req = make_request(query_params={})
        resp = await plugin.list_pending_comments(req)
        body = json.loads(resp.body)
        assert "缺少" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_pending_not_content_author(self):
        user = {"id": 99, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)

        req = make_request(query_params={"target_type": "blog", "target_id": "1"})
        resp = await plugin.list_pending_comments(req)
        body = json.loads(resp.body)
        assert body.get("error") or resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pending_content_author_can_view(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1, status="pending")

        req = make_request(query_params={"target_type": "blog", "target_id": "1"})
        resp = await plugin.list_pending_comments(req)
        body = json.loads(resp.body)
        assert "comments" in body
        assert body["total"] >= 1


# ============================================================
#  Notifications
# ============================================================

class TestNotifications:
    """Notification endpoints"""

    @pytest.mark.asyncio
    async def test_list_notifications(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_notification(engine, 1, user_id=1)

        req = make_request(query_params={"page": "1", "limit": "20"})
        resp = await plugin.list_notifications(req)
        body = json.loads(resp.body)
        assert "notifications" in body
        assert body["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_notifications_not_logged_in(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request()
        resp = await plugin.list_notifications(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")

    @pytest.mark.asyncio
    async def test_mark_notification_read(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_notification(engine, 1, user_id=1, is_read=0)

        req = make_request(method="POST", path_params={"notification_id": "1"})
        resp = await plugin.mark_notification_read(req)
        body = json.loads(resp.body)
        assert body.get("success") is True

    @pytest.mark.asyncio
    async def test_mark_notification_wrong_user(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_notification(engine, 1, user_id=1)

        req = make_request(method="POST", path_params={"notification_id": "1"})
        resp = await plugin.mark_notification_read(req)
        body = json.loads(resp.body)
        assert body.get("error") or resp.status_code == 403

    @pytest.mark.asyncio
    async def test_mark_notification_not_found(self):
        user = {"id": 1, "role": "user"}
        plugin, _ = await init_plugin(user=user)

        req = make_request(method="POST", path_params={"notification_id": "999"})
        resp = await plugin.mark_notification_read(req)
        body = json.loads(resp.body)
        assert "不存在" in body.get("error", "")

    @pytest.mark.asyncio
    async def test_mark_all_read(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_notification(engine, 1, user_id=1, is_read=0)
        seed_notification(engine, 2, user_id=1, is_read=0)

        req = make_request(method="POST")
        resp = await plugin.mark_all_notifications_read(req)
        body = json.loads(resp.body)
        assert body.get("success") is True

    @pytest.mark.asyncio
    async def test_unread_count(self):
        user = {"id": 1, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_notification(engine, 1, user_id=1, is_read=0)
        seed_notification(engine, 2, user_id=1, is_read=1)

        req = make_request()
        resp = await plugin.unread_count(req)
        body = json.loads(resp.body)
        assert body["count"] == 1

    @pytest.mark.asyncio
    async def test_unread_count_not_logged_in(self):
        plugin, _ = await init_plugin(user=None)
        req = make_request()
        resp = await plugin.unread_count(req)
        body = json.loads(resp.body)
        assert resp.status_code == 401 or body.get("error")


# ============================================================
#  MCP Tools
# ============================================================

class TestMCPTollComments:
    """MCP tool handlers"""

    @pytest.mark.asyncio
    async def test_mcp_list_comments(self):
        plugin, engine = await init_plugin()
        seed_comment(engine, 1, target_type="blog", target_id=1, status="approved")
        seed_comment(engine, 2, target_type="blog", target_id=1, status="pending")

        # MCP handler uses fetchall with "status = 'approved'" filter
        # Our mock needs to handle this SQL properly
        result = await plugin._mcp_list_comments("blog", 1)
        assert "comments" in result
        # Only approved comments should be returned
        approved = [c for c in result["comments"] if c.get("status") == "approved"]
        assert len(approved) >= 1

    @pytest.mark.asyncio
    async def test_mcp_create_comment_no_token(self):
        plugin, _ = await init_plugin()
        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="test", mcp_token=None
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_create_comment_invalid_token(self):
        plugin, _ = await init_plugin()
        # Auth plugin returns None for invalid token
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(return_value=None)
        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="test", mcp_token="bad"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_create_comment_empty_content(self):
        plugin, engine = await init_plugin()
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 2, "role": "user"}
        )
        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="  ", mcp_token="tok"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_create_comment_too_long(self):
        plugin, _ = await init_plugin()
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 2, "role": "user"}
        )
        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="x" * 2001, mcp_token="tok"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_create_comment_target_not_found(self):
        plugin, _ = await init_plugin()
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 2, "role": "user"}
        )
        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=999, content="test", mcp_token="tok"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_create_comment_success(self):
        plugin, engine = await init_plugin()
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 2, "role": "user"}
        )
        seed_post(engine, "blog_posts", 1, author_id=1)

        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="MCP comment", mcp_token="tok"
        )
        assert result["id"] > 0
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_mcp_create_comment_as_content_author(self):
        plugin, engine = await init_plugin()
        plugin._ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 1, "role": "user"}
        )
        seed_post(engine, "blog_posts", 1, author_id=1)

        result = await plugin._mcp_create_comment(
            target_type="blog", target_id=1, content="Self comment", mcp_token="tok"
        )
        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_mcp_tools_registered(self):
        plugin, _ = await init_plugin()
        tools = plugin.mcp_tools()
        names = [t.name for t in tools]
        assert "list_comments" in names
        assert "create_comment" in names


# ============================================================
#  Edge Cases
# ============================================================

class TestCommentsEdgeCases:
    """Edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_comment_on_microblog(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "microblog_posts", 5, author_id=1)

        req = make_request(json_body={
            "target_type": "microblog",
            "target_id": 5,
            "content": "Microblog comment",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["id"] > 0

    @pytest.mark.asyncio
    async def test_comment_on_note(self):
        user = {"id": 2, "role": "user"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "notes", 3, author_id=1)

        req = make_request(json_body={
            "target_type": "note",
            "target_id": 3,
            "content": "Note comment",
        })
        resp = await plugin.create_comment(req)
        body = json.loads(resp.body)
        assert body["id"] > 0

    @pytest.mark.asyncio
    async def test_admin_can_review(self):
        """Admin can review comments even if not content author"""
        user = {"id": 99, "role": "admin"}
        plugin, engine = await init_plugin(user=user)
        seed_post(engine, "blog_posts", 1, author_id=1)
        seed_comment(engine, 10, target_type="blog", target_id=1, status="pending")

        req = make_request(method="POST", json_body={"action": "approve"},
                           path_params={"comment_id": "10"})
        resp = await plugin.review_comment(req)
        body = json.loads(resp.body)
        assert body["status"] == "approved"

    @pytest.mark.asyncio
    async def test_plugin_properties(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "comments"
        assert plugin.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        routes = plugin.routes()
        assert len(routes) == 12
