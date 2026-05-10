"""Tests for plugins/nav/plugin.py — NavPlugin"""
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
        return None

    async def fetchall(self, sql, params=()):
        self._executed.append((sql, params))
        if "nav_links" in sql:
            results = []
            for link in self.tables.get("nav_links", {}).values():
                row = dict(link)
                # Apply visibility filter from SQL
                if "visibility = 'public'" in sql and row.get("visibility") != "public":
                    continue
                if "visibility = 'private'" in sql and row.get("visibility") != "private":
                    continue
                results.append(row)
            return results
        if "nav_link_hides" in sql:
            results = []
            uid = params[0] if params else None
            for h in self.tables.get("nav_link_hides", {}).values():
                if h.get("user_id") == uid:
                    results.append(dict(h))
            return results
        return []

    async def execute(self, sql, params=()):
        self._executed.append((sql, params))
        if "INSERT OR IGNORE INTO nav_link_hides" in sql:
            uid, lid = params[0], params[1]
            self._ensure_table("nav_link_hides")
            key = uid * 10000 + lid
            self.tables["nav_link_hides"][key] = {
                "id": key, "user_id": uid, "link_id": lid, "created_at": int(time.time())
            }
        if "DELETE FROM nav_link_hides WHERE user_id = ? AND link_id = ?" in sql:
            uid, lid = params[0], params[1]
            key = uid * 10000 + lid
            self.tables.get("nav_link_hides", {}).pop(key, None)
        if "DELETE FROM nav_link_hides WHERE link_id = ?" in sql:
            lid = params[0]
            to_delete = [k for k, v in self.tables.get("nav_link_hides", {}).items() if v.get("link_id") == lid]
            for k in to_delete:
                self.tables["nav_link_hides"].pop(k, None)


def seed_link(engine, link_id, title="Test", url="https://example.com",
              tags=None, visibility="public", author_id=1):
    now = int(time.time())
    data = {
        "id": link_id, "title": title, "url": url,
        "description": "", "icon": "",
        "tags": json.dumps(tags or [], ensure_ascii=False),
        "visibility": visibility, "author_id": author_id,
        "sort_order": 0, "created_at": now, "updated_at": now,
    }
    engine._ensure_table("nav_links")
    engine.tables["nav_links"][link_id] = data
    if link_id >= engine._next_id.get("nav_links", 1):
        engine._next_id["nav_links"] = link_id + 1
    return data


async def init_plugin(engine=None, user=None):
    from plugins.nav.plugin import NavPlugin
    plugin = NavPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.config = {}
    plugin.ctx = MagicMock()
    plugin.ctx.engine = engine
    plugin._ctx = plugin.ctx
    auth = MagicMock()
    auth.get_user_by_token = AsyncMock(return_value=user)
    auth.get_user_by_mcp_token = AsyncMock(return_value=user)
    plugin.ctx.get_plugin = MagicMock(return_value=auth)
    return plugin, engine


# ============================================================
#  Create Link
# ============================================================

class TestCreateLink:

    @pytest.mark.asyncio
    async def test_create_link_success(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_link(
            title="Google", url="https://google.com", author_id=1
        )
        assert result["id"] > 0
        assert result["title"] == "Google"

    @pytest.mark.asyncio
    async def test_create_link_with_tags(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_link(
            title="GitHub", url="https://github.com",
            tags=["dev", "git"], author_id=1
        )
        assert result["id"] > 0

    @pytest.mark.asyncio
    async def test_create_link_private(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_link(
            title="Secret", url="https://secret.com",
            visibility="private", author_id=1
        )
        assert result["id"] > 0

    @pytest.mark.asyncio
    async def test_create_link_mcp(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.create_link(
            title="MCP Link", url="https://mcp.com", mcp_token="tok"
        )
        assert result["id"] > 0


# ============================================================
#  Update Link
# ============================================================

class TestUpdateLink:

    @pytest.mark.asyncio
    async def test_update_title(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, author_id=1)
        result = await plugin.update_link(link_id=1, title="New Title", user_id=1)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_update_not_author(self):
        plugin, engine = await init_plugin(user={"id": 2})
        seed_link(engine, 1, author_id=1)
        result = await plugin.update_link(link_id=1, title="Hack", user_id=2)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_admin_allowed(self):
        plugin, engine = await init_plugin(user={"id": 99})
        seed_link(engine, 1, author_id=1)
        result = await plugin.update_link(link_id=1, title="Admin", user_id=99, is_admin=True)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.update_link(link_id=999, title="x", user_id=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_tags(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, author_id=1)
        result = await plugin.update_link(link_id=1, tags=["a", "b"], user_id=1)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_update_visibility(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, author_id=1, visibility="public")
        result = await plugin.update_link(link_id=1, visibility="private", user_id=1)
        assert result["ok"] is True


# ============================================================
#  Delete Link
# ============================================================

class TestDeleteLink:

    @pytest.mark.asyncio
    async def test_delete_by_author(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, author_id=1)
        result = await plugin.delete_link(link_id=1, user_id=1)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_by_admin(self):
        plugin, engine = await init_plugin(user={"id": 99})
        seed_link(engine, 1, author_id=1)
        result = await plugin.delete_link(link_id=1, user_id=99, is_admin=True)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_delete_unauthorized(self):
        plugin, engine = await init_plugin(user={"id": 2})
        seed_link(engine, 1, author_id=1)
        result = await plugin.delete_link(link_id=1, user_id=2)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        plugin, _ = await init_plugin(user={"id": 1})
        result = await plugin.delete_link(link_id=999, user_id=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_mcp(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, author_id=1)
        result = await plugin.delete_link(link_id=1, mcp_token="tok")
        assert result["ok"] is True


# ============================================================
#  Hide / Unhide
# ============================================================

class TestHideUnhide:

    @pytest.mark.asyncio
    async def test_hide_link(self):
        plugin, engine = await init_plugin(user={"id": 1})
        result = await plugin.hide_link(user_id=1, link_id=5)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_unhide_link(self):
        plugin, engine = await init_plugin(user={"id": 1})
        await plugin.hide_link(user_id=1, link_id=5)
        result = await plugin.unhide_link(user_id=1, link_id=5)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_get_hidden_ids(self):
        plugin, engine = await init_plugin(user={"id": 1})
        await plugin.hide_link(user_id=1, link_id=3)
        await plugin.hide_link(user_id=1, link_id=7)
        hidden = await plugin.get_hidden_ids(user_id=1)
        assert 3 in hidden
        assert 7 in hidden

    @pytest.mark.asyncio
    async def test_hide_idempotent(self):
        plugin, engine = await init_plugin(user={"id": 1})
        await plugin.hide_link(user_id=1, link_id=5)
        await plugin.hide_link(user_id=1, link_id=5)  # duplicate
        hidden = await plugin.get_hidden_ids(user_id=1)
        assert hidden == {5}


# ============================================================
#  List Links
# ============================================================

class TestListLinks:

    @pytest.mark.asyncio
    async def test_list_empty(self):
        plugin, _ = await init_plugin()
        result = await plugin.list_links()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_public(self):
        plugin, engine = await init_plugin()
        seed_link(engine, 1, visibility="public")
        seed_link(engine, 2, visibility="private")
        result = await plugin.list_links(visibility="public")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_with_tags_parsed(self):
        plugin, engine = await init_plugin()
        seed_link(engine, 1, tags=["dev", "python"])
        result = await plugin.list_links()
        assert isinstance(result[0]["tags"], list)

    @pytest.mark.asyncio
    async def test_list_mcp(self):
        plugin, engine = await init_plugin(user={"id": 1})
        seed_link(engine, 1, visibility="public")
        result = await plugin.list_links(visibility="public")
        assert isinstance(result, list)


# ============================================================
#  MCP Tools
# ============================================================

class TestMCPTollNav:

    @pytest.mark.asyncio
    async def test_mcp_tools_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.mcp_tools()) == 3

    @pytest.mark.asyncio
    async def test_mcp_tool_names(self):
        plugin, _ = await init_plugin()
        names = [t.name for t in plugin.mcp_tools()]
        assert "create_nav_link" in names
        assert "list_nav_links" in names
        assert "delete_nav_link" in names


# ============================================================
#  Plugin Properties
# ============================================================

class TestNavPluginProperties:

    @pytest.mark.asyncio
    async def test_name(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "nav"

    @pytest.mark.asyncio
    async def test_version(self):
        plugin, _ = await init_plugin()
        assert plugin.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.routes()) == 7
