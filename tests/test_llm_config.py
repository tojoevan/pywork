"""Tests for plugins/llm_config/plugin.py — LlmConfigPlugin"""
import pytest
import time
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
        if "llm_configs" in sql:
            if "WHERE id = ?" in sql:
                return self.tables.get("llm_configs", {}).get(params[0])
            if "is_default = 1" in sql:
                for c in self.tables.get("llm_configs", {}).values():
                    if c.get("is_default") == 1:
                        return dict(c)
        return None

    async def fetchall(self, sql, params=()):
        self._executed.append((sql, params))
        if "llm_configs" in sql:
            return [dict(r) for r in self.tables.get("llm_configs", {}).values()]
        return []

    async def execute(self, sql, params=()):
        self._executed.append((sql, params))
        if "UPDATE llm_configs SET is_default = 0" in sql:
            for c in self.tables.get("llm_configs", {}).values():
                c["is_default"] = 0
        if "DELETE FROM llm_configs WHERE id = ?" in sql:
            self.tables.get("llm_configs", {}).pop(params[0], None)


def seed_config(engine, config_id, name="test", base_url="https://api.openai.com/v1",
                api_key="sk-test123456789", model="gpt-4o", is_default=0):
    now = int(time.time())
    data = {
        "id": config_id, "name": name, "base_url": base_url,
        "api_key": api_key, "model": model, "temperature": 0.7,
        "max_tokens": 4096, "is_default": is_default,
        "system_prompt": "", "created_at": now, "updated_at": now,
    }
    engine._ensure_table("llm_configs")
    engine.tables["llm_configs"][config_id] = data
    if config_id >= engine._next_id.get("llm_configs", 1):
        engine._next_id["llm_configs"] = config_id + 1
    return data


async def init_plugin(engine=None):
    from plugins.llm_config.plugin import LlmConfigPlugin
    plugin = LlmConfigPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.config = {}
    plugin.ctx = MagicMock()
    plugin.ctx.engine = engine
    plugin._ctx = plugin.ctx
    auth = MagicMock()
    auth.get_user_by_mcp_token = AsyncMock(return_value={"id": 1, "role": "admin"})
    plugin.ctx.get_plugin = MagicMock(return_value=auth)
    return plugin, engine


# ============================================================
#  API Key Masking
# ============================================================

class TestMaskApiKey:

    @pytest.mark.asyncio
    async def test_mask_normal_key(self):
        plugin, _ = await init_plugin()
        result = plugin._mask_api_key("sk-1234567890abcdef")
        assert result.startswith("sk-1")
        assert result.endswith("cdef")
        assert "****" in result

    @pytest.mark.asyncio
    async def test_mask_short_key(self):
        plugin, _ = await init_plugin()
        assert plugin._mask_api_key("short") == "****"

    @pytest.mark.asyncio
    async def test_mask_empty_key(self):
        plugin, _ = await init_plugin()
        assert plugin._mask_api_key("") == "****"

    @pytest.mark.asyncio
    async def test_mask_none_key(self):
        plugin, _ = await init_plugin()
        assert plugin._mask_api_key(None) == "****"


# ============================================================
#  CRUD
# ============================================================

class TestLLMConfigCRUD:

    @pytest.mark.asyncio
    async def test_create_config(self):
        plugin, _ = await init_plugin()
        result = await plugin.create_config(
            name="openai", base_url="https://api.openai.com/v1",
            api_key="sk-test123456789"
        )
        assert result["id"] > 0
        assert result["name"] == "openai"

    @pytest.mark.asyncio
    async def test_create_config_as_default(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, is_default=1)
        result = await plugin.create_config(
            name="new", base_url="https://api.test.com/v1",
            api_key="sk-new123456789", is_default=True
        )
        # Old default should be cleared
        assert engine.tables["llm_configs"][1]["is_default"] == 0

    @pytest.mark.asyncio
    async def test_list_configs_masks_key(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, api_key="sk-secret123456789")
        result = await plugin.list_configs()
        assert len(result) == 1
        assert "api_key" not in result[0]
        assert "api_key_masked" in result[0]

    @pytest.mark.asyncio
    async def test_get_config_returns_real_key(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, api_key="sk-real123456789")
        result = await plugin.get_config(1)
        assert result["api_key"] == "sk-real123456789"

    @pytest.mark.asyncio
    async def test_get_default_config(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, is_default=0)
        seed_config(engine, 2, is_default=1)
        result = await plugin.get_default_config()
        assert result["id"] == 2

    @pytest.mark.asyncio
    async def test_update_config_name(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1)
        result = await plugin.update_config(id=1, name="renamed")
        assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_update_config_not_found(self):
        plugin, _ = await init_plugin()
        result = await plugin.update_config(id=999, name="x")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_config(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1)
        result = await plugin.delete_config(id=1)
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self):
        plugin, _ = await init_plugin()
        result = await plugin.delete_config(id=999)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_mcp_non_admin(self):
        plugin, _ = await init_plugin()
        plugin.ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(
            return_value={"id": 2, "role": "user"}
        )
        result = await plugin.create_config(
            name="test", base_url="https://api.test.com/v1",
            api_key="sk-test123", mcp_token="tok"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_mcp_invalid_token(self):
        plugin, _ = await init_plugin()
        plugin.ctx.get_plugin.return_value.get_user_by_mcp_token = AsyncMock(return_value=None)
        result = await plugin.create_config(
            name="test", base_url="https://api.test.com/v1",
            api_key="sk-test123", mcp_token="bad"
        )
        assert "error" in result


# ============================================================
#  Call LLM
# ============================================================

class TestCallLLM:

    @pytest.mark.asyncio
    async def test_call_llm_no_config(self):
        plugin, _ = await init_plugin()
        result = await plugin.call_llm(prompt="hello")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_llm_uses_default(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, is_default=1)
        # Mock the HTTP call
        plugin._do_llm_request = AsyncMock(return_value="Hello!")
        result = await plugin.call_llm(prompt="hi")
        assert result["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_call_llm_uses_specific_config(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, is_default=1)
        seed_config(engine, 2, model="claude-3")
        plugin._do_llm_request = AsyncMock(return_value="OK")
        result = await plugin.call_llm(prompt="hi", config_id=2)
        assert result["config_id"] == 2

    @pytest.mark.asyncio
    async def test_call_llm_request_error(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1, is_default=1)
        plugin._do_llm_request = AsyncMock(side_effect=Exception("timeout"))
        result = await plugin.call_llm(prompt="hi")
        assert "error" in result


# ============================================================
#  MCP Tools
# ============================================================

class TestMCPTollLLM:

    @pytest.mark.asyncio
    async def test_mcp_tools_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.mcp_tools()) == 6

    @pytest.mark.asyncio
    async def test_mcp_call_list(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1)
        result = await plugin.mcp_call("list_llm_configs", {})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_mcp_call_create(self):
        plugin, engine = await init_plugin()
        result = await plugin.mcp_call("create_llm_config", {
            "name": "test", "base_url": "https://api.test.com/v1",
            "api_key": "sk-test123"
        }, mcp_token="tok")
        assert result["id"] > 0

    @pytest.mark.asyncio
    async def test_mcp_call_delete(self):
        plugin, engine = await init_plugin()
        seed_config(engine, 1)
        result = await plugin.mcp_call("delete_llm_config", {"id": 1}, mcp_token="tok")
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_mcp_call_unknown(self):
        plugin, _ = await init_plugin()
        with pytest.raises(ValueError):
            await plugin.mcp_call("nonexistent", {})


# ============================================================
#  Plugin Properties
# ============================================================

class TestLLMConfigProperties:

    @pytest.mark.asyncio
    async def test_name(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "llm_config"

    @pytest.mark.asyncio
    async def test_version(self):
        plugin, _ = await init_plugin()
        assert plugin.version == "0.1.0"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        assert len(plugin.routes()) == 7
