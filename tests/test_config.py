"""Tests for app/config.py — AppConfig, SiteConfigManager, ConfigWrapper"""
import pytest
import os
import time
from unittest.mock import AsyncMock, MagicMock
from app.config import AppConfig, SiteConfigManager, ConfigWrapper, build_config, config_to_dict


# ============================================================
#  AppConfig
# ============================================================

class TestAppConfig:
    """Tests for Pydantic AppConfig model"""

    def test_default_values(self):
        config = AppConfig()
        assert config.title == "pyWork"
        assert config.port == 8080
        assert config.log_level == "INFO"
        assert config.debug is False

    def test_custom_values(self):
        config = AppConfig(title="My App", port=9090, debug=True)
        assert config.title == "My App"
        assert config.port == 9090
        assert config.debug is True

    def test_port_validation_valid(self):
        config = AppConfig(port=1)
        assert config.port == 1
        config = AppConfig(port=65535)
        assert config.port == 65535

    def test_port_validation_invalid(self):
        with pytest.raises(Exception):
            AppConfig(port=0)
        with pytest.raises(Exception):
            AppConfig(port=65536)

    def test_log_level_uppercase(self):
        config = AppConfig(log_level="debug")
        assert config.log_level == "DEBUG"

    def test_log_level_invalid(self):
        with pytest.raises(Exception):
            AppConfig(log_level="INVALID")

    def test_enabled_plugins_default(self):
        config = AppConfig()
        assert "blog" in config.enabled_plugins
        assert "auth" in config.enabled_plugins

    def test_github_fields_optional(self):
        config = AppConfig()
        assert config.github_client_id is None
        assert config.github_client_secret is None


# ============================================================
#  SiteConfigManager
# ============================================================

class TestSiteConfigManager:
    """Tests for SiteConfigManager"""

    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine.fetchall = AsyncMock(return_value=[])
        engine.execute = AsyncMock()
        return engine

    @pytest.fixture
    def manager(self, mock_engine):
        return SiteConfigManager(engine=mock_engine)

    @pytest.mark.asyncio
    async def test_load_empty(self, manager):
        result = await manager.load()
        assert result == {}

    @pytest.mark.asyncio
    async def test_load_from_db(self, mock_engine):
        mock_engine.fetchall = AsyncMock(return_value=[
            {"key": "title", "value": "Test"},
            {"key": "description", "value": "Desc"},
        ])
        manager = SiteConfigManager(engine=mock_engine)
        result = await manager.load()
        assert result["title"] == "Test"
        assert result["description"] == "Desc"

    @pytest.mark.asyncio
    async def test_load_cache_hit(self, mock_engine):
        call_count = 0
        original_fetchall = mock_engine.fetchall

        async def counting_fetchall(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return [{"key": "title", "value": "Test"}]

        mock_engine.fetchall = counting_fetchall
        manager = SiteConfigManager(engine=mock_engine)

        await manager.load()
        await manager.load()  # should use cache
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_load_cache_expired(self, mock_engine):
        call_count = 0

        async def counting_fetchall(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return [{"key": "title", "value": "Test"}]

        mock_engine.fetchall = counting_fetchall
        manager = SiteConfigManager(engine=mock_engine)
        manager._cache_ttl = 0  # expire immediately

        await manager.load()
        await manager.load()  # should re-fetch
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_existing(self, manager, mock_engine):
        mock_engine.fetchall = AsyncMock(return_value=[
            {"key": "title", "value": "Test"},
        ])
        result = await manager.get("title")
        assert result == "Test"

    @pytest.mark.asyncio
    async def test_get_default(self, manager):
        result = await manager.get("nonexistent", "default")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_set_value(self, manager, mock_engine):
        await manager.set("title", "New Title")
        assert mock_engine.execute.call_count >= 1
        assert manager._cache is None  # cache invalidated

    @pytest.mark.asyncio
    async def test_batch_set(self, manager, mock_engine):
        await manager.batch_set({"title": "T", "description": "D"})
        # 1 CREATE TABLE + 2 INSERT = 3
        assert mock_engine.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_set_with_allowed_keys(self, manager, mock_engine):
        await manager.batch_set(
            {"title": "T", "secret": "S"},
            allowed_keys=["title"]
        )
        # 1 CREATE TABLE + 1 INSERT = 2
        assert mock_engine.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_all(self, manager, mock_engine):
        mock_engine.fetchall = AsyncMock(return_value=[
            {"key": "title", "value": "T"},
        ])
        result = await manager.get_all()
        assert result == {"title": "T"}
        # Mutating the copy shouldn't affect cache
        result["title"] = "X"
        assert (await manager.get_all())["title"] == "T"

    def test_invalidate_cache(self, manager):
        manager._cache = {"key": "value"}
        manager.invalidate_cache()
        assert manager._cache is None

    def test_set_engine(self):
        manager = SiteConfigManager()
        assert manager._engine is None
        engine = MagicMock()
        manager.set_engine(engine)
        assert manager._engine is engine

    @pytest.mark.asyncio
    async def test_no_engine(self):
        manager = SiteConfigManager()
        await manager.set("key", "value")  # should not raise
        result = await manager.get("key")
        assert result == ""


# ============================================================
#  ConfigWrapper
# ============================================================

class TestConfigWrapper:
    """Tests for ConfigWrapper dict-style access"""

    @pytest.fixture
    def wrapper(self):
        return ConfigWrapper(AppConfig(title="Test", port=9090))

    def test_attribute_access(self, wrapper):
        assert wrapper.title == "Test"
        assert wrapper.port == 9090

    def test_getitem(self, wrapper):
        assert wrapper["title"] == "Test"

    def test_get(self, wrapper):
        assert wrapper.get("title") == "Test"
        assert wrapper.get("nonexistent", "default") == "default"

    def test_contains(self, wrapper):
        assert "title" in wrapper
        assert "nonexistent" not in wrapper

    def test_items(self, wrapper):
        items = dict(wrapper.items())
        assert items["title"] == "Test"
        assert items["port"] == 9090

    def test_keys(self, wrapper):
        assert "title" in wrapper.keys()
        assert "port" in wrapper.keys()

    def test_values(self, wrapper):
        assert "Test" in wrapper.values()

    def test_getitem_key_error(self, wrapper):
        with pytest.raises(KeyError):
            _ = wrapper["nonexistent"]

    def test_attribute_error(self, wrapper):
        with pytest.raises(AttributeError):
            _ = wrapper.nonexistent


# ============================================================
#  config_to_dict
# ============================================================

class TestConfigToDict:
    """Tests for config_to_dict"""

    def test_returns_dict(self):
        config = AppConfig(title="Test")
        result = config_to_dict(config)
        assert isinstance(result, dict)
        assert result["title"] == "Test"
        assert "port" in result
