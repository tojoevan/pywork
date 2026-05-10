"""Tests for plugins/board/plugin.py — BoardPlugin"""
import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional


class MockEngine:
    def __init__(self):
        self.tables: Dict[str, Dict[int, Dict]] = {}
        self._next_id: Dict[str, int] = {}
        self._executed: List[tuple] = []

    def _ensure_table(self, table):
        if table not in self.tables:
            self.tables[table] = {}
            self._next_id[table] = 1

    async def get(self, table, id):
        self._ensure_table(table)
        row = self.tables[table].get(id)
        return dict(row) if row else None

    async def put(self, table, id, data):
        self._ensure_table(table)
        if id == 0:
            id = self._next_id[table]
            self._next_id[table] += 1
        data = data.copy()
        data["id"] = id
        self.tables[table][id] = data
        return id

    async def delete(self, table, id):
        self._ensure_table(table)
        self.tables[table].pop(id, None)

    async def fetchone(self, sql, params=()):
        self._executed.append((sql, params))
        if "cron_jobs WHERE id" in sql:
            return self.tables.get("cron_jobs", {}).get(params[0])
        if "COUNT(*)" in sql:
            return {"cnt": 0}
        return None

    async def fetchall(self, sql, params=()):
        self._executed.append((sql, params))
        if "cron_stats" in sql:
            return [dict(r) for r in self.tables.get("cron_stats", {}).values()]
        if "cron_jobs" in sql:
            return [dict(r) for r in self.tables.get("cron_jobs", {}).values()]
        if "active_authors" in sql:
            return [dict(r) for r in self.tables.get("active_authors", {}).values()]
        if "hot_tags" in sql:
            return [dict(r) for r in self.tables.get("hot_tags", {}).values()]
        if "recent_comments" in sql:
            return [dict(r) for r in self.tables.get("recent_comments", {}).values()]
        if "blog_posts" in sql and "COUNT(*)" in sql:
            return [{"cnt": len(self.tables.get("blog_posts", {}))}]
        if "microblog_posts" in sql and "COUNT(*)" in sql:
            return [{"cnt": len(self.tables.get("microblog_posts", {}))}]
        if "notes" in sql and "COUNT(*)" in sql:
            return [{"cnt": len(self.tables.get("notes", {}))}]
        if "board_tasks" in sql:
            return [dict(r) for r in self.tables.get("board_tasks", {}).values()]
        if "comments" in sql:
            return []
        if "guestbook_entries" in sql:
            return []
        return []

    async def execute(self, sql, params=()):
        self._executed.append((sql, params))
        if "INSERT OR REPLACE INTO cron_stats" in sql:
            key, value = params[0], params[1]
            self._ensure_table("cron_stats")
            self.tables["cron_stats"][key] = {
                "id": key, "stat_key": key, "stat_value": value, "updated_at": int(time.time())
            }
        if "DELETE FROM hot_tags" in sql:
            self.tables.pop("hot_tags", None)
        if "INSERT INTO hot_tags" in sql:
            self._ensure_table("hot_tags")
            tag_name, post_count, rank = params[0], params[1], params[2]
            self.tables["hot_tags"][rank] = {
                "id": rank, "tag_name": tag_name, "post_count": post_count,
                "rank": rank, "updated_at": int(time.time())
            }
        if "DELETE FROM recent_comments" in sql:
            self.tables.pop("recent_comments", None)


def seed_cron_job(engine, job_id, name="test", handler_key="run_stats_collection",
                  interval_sec=3600, enabled=1):
    now = int(time.time())
    data = {
        "id": job_id, "name": name, "description": "",
        "handler_key": handler_key, "interval_sec": interval_sec,
        "cron_expr": "", "enabled": enabled,
        "last_run_at": 0, "next_run_at": now + interval_sec,
        "last_result": "", "run_count": 0,
        "created_at": now, "updated_at": now,
    }
    engine._ensure_table("cron_jobs")
    engine.tables["cron_jobs"][job_id] = data
    if job_id >= engine._next_id.get("cron_jobs", 1):
        engine._next_id["cron_jobs"] = job_id + 1
    return data


def seed_cron_stats(engine, key, value):
    engine._ensure_table("cron_stats")
    engine.tables["cron_stats"][key] = {
        "id": key, "stat_key": key, "stat_value": str(value),
        "updated_at": int(time.time()),
    }


async def init_plugin(engine=None, user=None):
    from plugins.board.plugin import BoardPlugin
    plugin = BoardPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.template_engine = MagicMock()
    plugin.template_engine.render = AsyncMock(return_value="<html></html>")
    plugin.config = {}
    plugin.ctx = MagicMock()
    plugin.ctx.engine = engine
    plugin._ctx = plugin.ctx
    plugin._tables_initialized = True  # skip table creation
    plugin._handlers = {}

    auth = MagicMock()
    auth.get_user_by_token = AsyncMock(return_value=user)
    plugin.ctx.get_plugin = MagicMock(return_value=auth)

    from app.log import get_logger
    plugin._cron_log = get_logger("test.cron", "cron")

    return plugin, engine


# ============================================================
#  Stats
# ============================================================

class TestGetStats:

    @pytest.mark.asyncio
    async def test_stats_from_cache(self):
        plugin, engine = await init_plugin()
        seed_cron_stats(engine, "blog_count", 5)
        seed_cron_stats(engine, "microblog_count", 3)
        seed_cron_stats(engine, "note_count", 2)
        seed_cron_stats(engine, "total_count", 10)
        seed_cron_stats(engine, "stats_updated_at", int(time.time()))

        stats = await plugin.get_stats()
        assert stats["blog_count"] == 5
        assert stats["total_count"] == 10

    @pytest.mark.asyncio
    async def test_stats_empty_live(self):
        plugin, engine = await init_plugin()
        stats = await plugin.get_stats()
        assert stats["blog_count"] == 0
        assert stats["total_count"] == 0


# ============================================================
#  Active Authors
# ============================================================

class TestActiveAuthors:

    @pytest.mark.asyncio
    async def test_empty_authors(self):
        plugin, _ = await init_plugin()
        result = await plugin.get_active_authors()
        assert result == []

    @pytest.mark.asyncio
    async def test_authors_from_cache(self):
        plugin, engine = await init_plugin()
        now = int(time.time())
        engine._ensure_table("active_authors")
        engine.tables["active_authors"][1] = {
            "id": 1, "author_id": 1, "author_name": "Alice",
            "author_avatar": "", "blog_count": 5, "microblog_count": 3,
            "note_count": 2, "rank": 1, "period": "monthly",
            "updated_at": now,
        }
        result = await plugin.get_active_authors()
        assert len(result) == 1
        assert result[0]["author_name"] == "Alice"


# ============================================================
#  Hot Tags
# ============================================================

class TestHotTags:

    @pytest.mark.asyncio
    async def test_empty_hot_tags(self):
        plugin, engine = await init_plugin()
        result = await plugin.get_hot_tags()
        assert result == []

    @pytest.mark.asyncio
    async def test_hot_tags_from_cache(self):
        plugin, engine = await init_plugin()
        now = int(time.time())
        engine._ensure_table("hot_tags")
        engine.tables["hot_tags"][1] = {
            "id": 1, "tag_name": "python", "post_count": 10,
            "rank": 1, "updated_at": now,
        }
        result = await plugin.get_hot_tags()
        assert len(result) == 1
        assert result[0]["tag_name"] == "python"


# ============================================================
#  Cron Job CRUD
# ============================================================

class TestCronJobs:

    @pytest.mark.asyncio
    async def test_list_cron_jobs_empty(self):
        plugin, _ = await init_plugin()
        jobs = await plugin._list_cron_jobs()
        assert jobs == []

    @pytest.mark.asyncio
    async def test_create_cron_job(self):
        plugin, engine = await init_plugin()
        job_id = await plugin._create_cron_job(
            name="Test Job", handler_key="run_stats_collection"
        )
        assert job_id > 0

    @pytest.mark.asyncio
    async def test_get_cron_job(self):
        plugin, engine = await init_plugin()
        seed_cron_job(engine, 1, name="My Job")
        job = await plugin._get_cron_job(1)
        assert job["name"] == "My Job"

    @pytest.mark.asyncio
    async def test_get_cron_job_not_found(self):
        plugin, _ = await init_plugin()
        job = await plugin._get_cron_job(999)
        assert job is None

    @pytest.mark.asyncio
    async def test_delete_cron_job(self):
        plugin, engine = await init_plugin()
        seed_cron_job(engine, 1)
        await plugin._delete_cron_job(1)
        job = await plugin._get_cron_job(1)
        assert job is None


# ============================================================
#  Plugin Properties
# ============================================================

class TestBoardPluginProperties:

    @pytest.mark.asyncio
    async def test_name(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "board"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.routes()) == 20


# ============================================================
#  Preset Jobs
# ============================================================

class TestPresetJobs:

    def test_preset_jobs_defined(self):
        from plugins.board.plugin import PRESET_JOBS
        assert "stats_collection" in PRESET_JOBS
        assert "active_authors" in PRESET_JOBS
        assert "hot_tags" in PRESET_JOBS
        assert "recent_comments" in PRESET_JOBS

    def test_interval_options(self):
        from plugins.board.plugin import INTERVAL_OPTIONS
        assert len(INTERVAL_OPTIONS) >= 5
