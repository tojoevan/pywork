"""Tests for plugins/topic/plugin.py — TopicPlugin"""
import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional


# ============================================================
#  Mock Engine
# ============================================================

class MockEngine:
    """In-memory mock engine for topic tests"""

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
        # topic_discussions queries (also handles JOIN queries)
        if "topic_discussions" in sql and ("WHERE t.id = ?" in sql or "WHERE id = ?" in sql):
            tid = params[0] if params else None
            topic = self.tables.get("topic_discussions", {}).get(tid)
            if topic:
                result = dict(topic)
                # Add author info from users table
                user = self.tables.get("users", {}).get(topic.get("author_id"))
                if user:
                    result["author_name"] = user.get("nickname") or user.get("username", "unknown")
                    result["author_avatar"] = user.get("avatar", "")
                # Add vote counts
                result["reply_count"] = sum(1 for r in self.tables.get("topic_replies", {}).values() if r.get("topic_id") == tid)
                result["upvote_count"] = sum(1 for v in self.tables.get("topic_votes", {}).values() if v.get("target_type") == "topic" and v.get("target_id") == tid and v.get("vote_type") == "upvote")
                result["downvote_count"] = sum(1 for v in self.tables.get("topic_votes", {}).values() if v.get("target_type") == "topic" and v.get("target_id") == tid and v.get("vote_type") == "downvote")
                return result
            return None
        # COUNT queries
        if "COUNT(*)" in sql and "topic_discussions" in sql:
            count = 0
            for t in self.tables.get("topic_discussions", {}).values():
                if "status = ?" in sql:
                    if t.get("status") == params[0]:
                        count += 1
                else:
                    count += 1
            return {"cnt": count}
        # users role lookup
        if "users" in sql and "role" in sql:
            uid = params[0] if params else None
            user = self.tables.get("users", {}).get(uid)
            if user:
                return {"role": user.get("role", "user")}
            return None
        # topic_votes existing vote
        if "topic_votes" in sql and "target_type" in sql:
            target_type, target_id, author_id = params
            for v in self.tables.get("topic_votes", {}).values():
                if (v.get("target_type") == target_type and
                    v.get("target_id") == target_id and
                    v.get("author_id") == author_id):
                    return dict(v)
            return None
        return None

    async def fetchall(self, sql: str, params: tuple = ()) -> List[Dict]:
        self._executed.append((sql, params))
        results = []

        # topic_discussions list queries
        if "topic_discussions" in sql and "ORDER BY" in sql:
            status_filter = None
            if "status = ?" in sql:
                status_filter = params[0]
            # Extract LIMIT from params (last two params are limit, offset)
            limit = None
            if "LIMIT" in sql:
                limit = params[-2] if len(params) >= 2 else None
            count = 0
            for t in self.tables.get("topic_discussions", {}).values():
                if status_filter and t.get("status") != status_filter:
                    continue
                if limit is not None and count >= limit:
                    break
                count += 1
                row = dict(t)
                user = self.tables.get("users", {}).get(t.get("author_id"))
                if user:
                    row["author_name"] = user.get("nickname") or user.get("username", "unknown")
                    row["author_avatar"] = user.get("avatar", "")
                row["reply_count"] = 0
                row["upvote_count"] = 0
                row["downvote_count"] = 0
                # Count replies
                for r in self.tables.get("topic_replies", {}).values():
                    if r.get("topic_id") == t["id"]:
                        row["reply_count"] += 1
                # Count votes
                for v in self.tables.get("topic_votes", {}).values():
                    if v.get("target_type") == "topic" and v.get("target_id") == t["id"]:
                        if v.get("vote_type") == "upvote":
                            row["upvote_count"] += 1
                        elif v.get("vote_type") == "downvote":
                            row["downvote_count"] += 1
                results.append(row)
            return results

        # topic_replies list
        if "topic_replies" in sql and "topic_id" in sql:
            tid = params[0] if params else None
            for r in self.tables.get("topic_replies", {}).values():
                if r.get("topic_id") == tid:
                    row = dict(r)
                    user = self.tables.get("users", {}).get(r.get("author_id"))
                    if user:
                        row["author_name"] = user.get("nickname") or user.get("username", "unknown")
                    row["upvote_count"] = 0
                    row["downvote_count"] = 0
                    for v in self.tables.get("topic_votes", {}).values():
                        if v.get("target_type") == "reply" and v.get("target_id") == r["id"]:
                            if v.get("vote_type") == "upvote":
                                row["upvote_count"] += 1
                            elif v.get("vote_type") == "downvote":
                                row["downvote_count"] += 1
                    results.append(row)
            return results

        # topic_votes for user
        if "topic_votes" in sql and "author_id" in sql:
            uid = params[0] if params else None
            for v in self.tables.get("topic_votes", {}).values():
                if v.get("author_id") == uid:
                    results.append(dict(v))
            return results

        # expired topics
        if "topic_discussions" in sql and "status = 'open'" in sql:
            now = params[0] if params else 0
            for t in self.tables.get("topic_discussions", {}).values():
                if t.get("status") == "open" and t.get("deadline", 0) < now:
                    results.append(dict(t))
            return results

        return results

    async def execute(self, sql: str, params: tuple = ()) -> None:
        self._executed.append((sql, params))
        # UPDATE topic_discussions
        if "UPDATE topic_discussions SET" in sql:
            tid = params[-1] if params else None
            topic = self.tables.get("topic_discussions", {}).get(tid)
            if topic:
                if "status = 'closed'" in sql:
                    topic["status"] = "closed"
                if "status = 'summarized'" in sql:
                    topic["status"] = "summarized"
                if "summary" in sql:
                    topic["summary"] = params[0] if params else ""
                if "updated_at" in sql:
                    topic["updated_at"] = params[0] if len(params) > 0 else int(time.time())
        # DELETE topic_votes
        if "DELETE FROM topic_votes WHERE id = ?" in sql:
            vid = params[0] if params else None
            self.tables.get("topic_votes", {}).pop(vid, None)
        # UPDATE topic_votes
        if "UPDATE topic_votes SET vote_type" in sql:
            vid = params[-1] if params else None
            vote = self.tables.get("topic_votes", {}).get(vid)
            if vote:
                vote["vote_type"] = params[0]
                vote["created_at"] = params[1]


# ============================================================
#  Helpers
# ============================================================

def make_request(method="GET", path="/topic", query_params=None,
                 cookies=None, json_body=None, headers=None, path_params=None):
    req = MagicMock()
    req.method = method
    req.url = MagicMock()
    req.url.path = path
    req.query_params = query_params or {}
    req.cookies = cookies or {}
    req.headers = headers or {"content-type": "application/json"}
    req.path_params = path_params or {}
    if json_body is not None:
        req.json = AsyncMock(return_value=json_body)
        req.form = AsyncMock(return_value=json_body)
    else:
        req.json = AsyncMock(side_effect=Exception("no body"))
        req.form = AsyncMock(return_value={})
    return req


async def init_plugin(engine=None, user=None):
    from plugins.topic.plugin import TopicPlugin

    plugin = TopicPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.config = {}
    plugin.ctx = MagicMock()
    plugin.ctx.engine = engine
    plugin._ctx = plugin.ctx

    auth_mock = MagicMock()
    auth_mock.get_user_by_token = AsyncMock(return_value=user)
    auth_mock.get_user_by_mcp_token = AsyncMock(return_value=user)
    plugin.ctx.get_plugin = MagicMock(return_value=auth_mock)

    return plugin, engine


def seed_topic(engine, topic_id, author_id=1, title="Test Topic",
               description="desc", status="open", deadline_hours=72):
    now = int(time.time())
    data = {
        "id": topic_id,
        "author_id": author_id,
        "title": title,
        "description": description,
        "status": status,
        "deadline": now + deadline_hours * 3600,
        "summary": "",
        "summary_post_id": None,
        "created_at": now,
        "updated_at": now,
    }
    engine._ensure_table("topic_discussions")
    engine.tables["topic_discussions"][topic_id] = data
    if topic_id >= engine._next_id.get("topic_discussions", 1):
        engine._next_id["topic_discussions"] = topic_id + 1
    return data


def seed_user(engine, user_id, role="user", username="testuser"):
    engine._ensure_table("users")
    engine.tables["users"][user_id] = {
        "id": user_id,
        "username": username,
        "nickname": username,
        "role": role,
        "avatar": "",
    }


def seed_reply(engine, reply_id, topic_id, author_id=2, content="reply"):
    now = int(time.time())
    data = {
        "id": reply_id,
        "topic_id": topic_id,
        "author_id": author_id,
        "content": content,
        "parent_id": None,
        "created_at": now,
        "updated_at": now,
    }
    engine._ensure_table("topic_replies")
    engine.tables["topic_replies"][reply_id] = data
    return data


def seed_vote(engine, vote_id, target_type, target_id, author_id, vote_type):
    now = int(time.time())
    data = {
        "id": vote_id,
        "target_type": target_type,
        "target_id": target_id,
        "author_id": author_id,
        "vote_type": vote_type,
        "created_at": now,
    }
    engine._ensure_table("topic_votes")
    engine.tables["topic_votes"][vote_id] = data
    return data


# ============================================================
#  Create Topic
# ============================================================

class TestCreateTopic:

    @pytest.mark.asyncio
    async def test_create_topic_success(self):
        plugin, _ = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.create_topic(
            title="Test Topic", description="A test", author_id=1
        )
        assert result["id"] > 0
        assert result["title"] == "Test Topic"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_create_topic_no_author(self):
        plugin, _ = await init_plugin(user=None)
        result = await plugin.create_topic(title="Test")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_topic_custom_deadline(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_topic(
            title="Test", deadline_hours=24, author_id=1
        )
        assert result["deadline_hours"] == 24

    @pytest.mark.asyncio
    async def test_create_topic_mcp(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_topic(
            title="MCP Topic", mcp_token="tok"
        )
        assert result["id"] > 0

    @pytest.mark.asyncio
    async def test_create_topic_mcp_invalid_token(self):
        plugin, _ = await init_plugin()
        plugin.ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(return_value=None)
        result = await plugin.create_topic(title="Test", mcp_token="bad")
        assert "error" in result


# ============================================================
#  Update Topic
# ============================================================

class TestUpdateTopic:

    @pytest.mark.asyncio
    async def test_update_title(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, author_id=1)

        result = await plugin.update_topic(topic_id=1, title="New Title", author_id=1)
        assert result["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_description(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, author_id=1)

        result = await plugin.update_topic(topic_id=1, description="New desc", author_id=1)
        assert result["description"] == "New desc"

    @pytest.mark.asyncio
    async def test_update_not_author(self):
        plugin, engine = await init_plugin(user={"id": 2})
        seed_topic(engine, 1, author_id=1)
        seed_user(engine, 2, role="user")

        result = await plugin.update_topic(topic_id=1, title="Hack", author_id=2)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_admin_allowed(self):
        plugin, engine = await init_plugin(user={"id": 99, "role": "admin"})
        seed_topic(engine, 1, author_id=1)
        seed_user(engine, 99, role="admin")

        result = await plugin.update_topic(topic_id=1, title="Admin Edit", author_id=99)
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_update_closed_topic(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, author_id=1, status="closed")

        result = await plugin.update_topic(topic_id=1, title="Nope", author_id=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_nonexistent(self):
        plugin, engine = await init_plugin(user={"id": 1})
        result = await plugin.update_topic(topic_id=999, title="x", author_id=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_empty_title(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, author_id=1)

        result = await plugin.update_topic(topic_id=1, title="  ", author_id=1)
        assert "error" in result


# ============================================================
#  Reply Topic
# ============================================================

class TestReplyTopic:

    @pytest.mark.asyncio
    async def test_reply_success(self):
        plugin, engine = await init_plugin(user={"id": 2})
        seed_topic(engine, 1, author_id=1, status="open")

        result = await plugin.reply_topic(
            topic_id=1, content="Great idea!", author_id=2
        )
        assert result["id"] > 0
        assert result["topic_id"] == 1

    @pytest.mark.asyncio
    async def test_reply_no_author(self):
        plugin, engine = await init_plugin(user=None)
        seed_topic(engine, 1)

        result = await plugin.reply_topic(topic_id=1, content="test")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reply_closed_topic(self):
        plugin, engine = await init_plugin(user={"id": 2})
        seed_topic(engine, 1, status="closed")

        result = await plugin.reply_topic(
            topic_id=1, content="too late", author_id=2
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reply_nonexistent_topic(self):
        plugin, _ = await init_plugin(user={"id": 2})
        result = await plugin.reply_topic(
            topic_id=999, content="test", author_id=2
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reply_with_parent(self):
        plugin, engine = await init_plugin(user={"id": 3})
        seed_topic(engine, 1, status="open")
        seed_reply(engine, 10, topic_id=1, author_id=2)

        result = await plugin.reply_topic(
            topic_id=1, content="Nested reply", parent_id=10, author_id=3
        )
        assert result["id"] > 0


# ============================================================
#  Vote
# ============================================================

class TestVote:

    @pytest.mark.asyncio
    async def test_upvote_new(self):
        plugin, engine = await init_plugin(user={"id": 2})
        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="upvote", author_id=2
        )
        assert result["action"] == "added"
        assert result["vote_type"] == "upvote"

    @pytest.mark.asyncio
    async def test_downvote_new(self):
        plugin, engine = await init_plugin(user={"id": 2})
        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="downvote", author_id=2
        )
        assert result["action"] == "added"

    @pytest.mark.asyncio
    async def test_vote_toggle_off(self):
        """Same vote again removes it"""
        plugin, engine = await init_plugin(user={"id": 2})
        seed_vote(engine, 1, "topic", 1, 2, "upvote")

        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="upvote", author_id=2
        )
        assert result["action"] == "removed"

    @pytest.mark.asyncio
    async def test_vote_change(self):
        """Changing vote type"""
        plugin, engine = await init_plugin(user={"id": 2})
        seed_vote(engine, 1, "topic", 1, 2, "upvote")

        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="downvote", author_id=2
        )
        assert result["action"] == "changed"
        assert result["vote_type"] == "downvote"

    @pytest.mark.asyncio
    async def test_vote_no_author(self):
        plugin, _ = await init_plugin(user=None)
        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="upvote"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_vote_on_reply(self):
        plugin, engine = await init_plugin(user={"id": 2})
        result = await plugin.vote(
            target_type="reply", target_id=5,
            vote_type="upvote", author_id=2
        )
        assert result["action"] == "added"

    @pytest.mark.asyncio
    async def test_vote_mcp(self):
        plugin, engine = await init_plugin(user={"id": 2})
        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="upvote", mcp_token="tok"
        )
        assert "action" in result

    @pytest.mark.asyncio
    async def test_vote_mcp_invalid_token(self):
        plugin, _ = await init_plugin()
        plugin.ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(return_value=None)
        result = await plugin.vote(
            target_type="topic", target_id=1,
            vote_type="upvote", mcp_token="bad"
        )
        assert "error" in result


# ============================================================
#  Get Topic Detail
# ============================================================

class TestGetTopicDetail:

    @pytest.mark.asyncio
    async def test_get_existing_topic(self):
        plugin, engine = await init_plugin()
        seed_topic(engine, 1, author_id=1, title="Detail Test")
        seed_user(engine, 1, username="author")

        result = await plugin.get_topic_detail(topic_id=1)
        assert result["title"] == "Detail Test"
        assert "replies" in result

    @pytest.mark.asyncio
    async def test_get_nonexistent_topic(self):
        plugin, _ = await init_plugin()
        result = await plugin.get_topic_detail(topic_id=999)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_topic_with_replies(self):
        plugin, engine = await init_plugin()
        seed_topic(engine, 1)
        seed_reply(engine, 10, topic_id=1, content="Reply 1")
        seed_reply(engine, 11, topic_id=1, content="Reply 2")

        result = await plugin.get_topic_detail(topic_id=1)
        assert len(result["replies"]) == 2

    @pytest.mark.asyncio
    async def test_get_topic_with_votes(self):
        plugin, engine = await init_plugin()
        seed_topic(engine, 1)
        seed_vote(engine, 1, "topic", 1, 2, "upvote")
        seed_vote(engine, 2, "topic", 1, 3, "downvote")

        result = await plugin.get_topic_detail(topic_id=1)
        assert result["upvote_count"] >= 1
        assert result["downvote_count"] >= 1

    @pytest.mark.asyncio
    async def test_remaining_hours(self):
        plugin, engine = await init_plugin()
        seed_topic(engine, 1, deadline_hours=48)

        result = await plugin.get_topic_detail(topic_id=1)
        assert result["remaining_hours"] > 0


# ============================================================
#  Close Topic
# ============================================================

class TestCloseTopic:

    @pytest.mark.asyncio
    async def test_close_open_topic(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, status="open")

        result = await plugin.close_topic(topic_id=1)
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_topic(engine, 1, status="closed")

        result = await plugin.close_topic(topic_id=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_close_nonexistent(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.close_topic(topic_id=999)
        assert "error" in result


# ============================================================
#  List Topics
# ============================================================

class TestListTopics:

    @pytest.mark.asyncio
    async def test_list_empty(self):
        plugin, _ = await init_plugin()
        result = await plugin.list_topics()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_multiple(self):
        plugin, engine = await init_plugin()
        seed_user(engine, 1, username="author")
        seed_topic(engine, 1, title="Topic A")
        seed_topic(engine, 2, title="Topic B")

        result = await plugin.list_topics()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self):
        plugin, engine = await init_plugin()
        seed_user(engine, 1)
        seed_topic(engine, 1, status="open")
        seed_topic(engine, 2, status="closed")

        result = await plugin.list_topics(status="open")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_limit(self):
        plugin, engine = await init_plugin()
        seed_user(engine, 1)
        for i in range(5):
            seed_topic(engine, i + 1)

        result = await plugin.list_topics(limit=3)
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_list_remaining_hours(self):
        plugin, engine = await init_plugin()
        seed_user(engine, 1)
        seed_topic(engine, 1, deadline_hours=24)

        result = await plugin.list_topics()
        assert len(result) == 1
        assert result[0]["remaining_hours"] > 0


# ============================================================
#  Mark Expired Topics
# ============================================================

class TestMarkExpired:

    @pytest.mark.asyncio
    async def test_mark_expired(self):
        plugin, engine = await init_plugin()
        now = int(time.time())
        # Create a topic that already expired
        seed_topic(engine, 1, deadline_hours=-1)  # already past

        count = await plugin._mark_expired_topics()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_no_expired(self):
        plugin, engine = await init_plugin()
        seed_topic(engine, 1, deadline_hours=72)  # future

        count = await plugin._mark_expired_topics()
        assert count == 0


# ============================================================
#  MCP Tools
# ============================================================

class TestMCPTollTopic:

    @pytest.mark.asyncio
    async def test_mcp_tools_count(self):
        plugin, _ = await init_plugin()
        tools = plugin.mcp_tools()
        assert len(tools) == 7

    @pytest.mark.asyncio
    async def test_mcp_tool_names(self):
        plugin, _ = await init_plugin()
        names = [t.name for t in plugin.mcp_tools()]
        assert "create_topic" in names
        assert "update_topic" in names
        assert "list_topics" in names
        assert "reply_topic" in names
        assert "vote" in names
        assert "get_topic_detail" in names
        assert "summarize_topic" in names

    @pytest.mark.asyncio
    async def test_mcp_call_create(self):
        plugin, engine = await init_plugin(user={"id": 1})
        result = await plugin.mcp_call("create_topic", {"title": "MCP"}, mcp_token="tok")
        assert result["id"] > 0

    @pytest.mark.asyncio
    async def test_mcp_call_list(self):
        plugin, engine = await init_plugin()
        result = await plugin.mcp_call("list_topics", {})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_mcp_call_unknown_tool(self):
        plugin, _ = await init_plugin()
        with pytest.raises(ValueError, match="Unknown"):
            await plugin.mcp_call("nonexistent_tool", {})


# ============================================================
#  Plugin Properties
# ============================================================

class TestTopicPluginProperties:

    @pytest.mark.asyncio
    async def test_plugin_name(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "topic"

    @pytest.mark.asyncio
    async def test_plugin_version(self):
        plugin, _ = await init_plugin()
        assert plugin.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.routes()) == 11
