"""Pytest configuration and fixtures for pyWork tests"""
import pytest
import os
import sys
import tempfile
import asyncio

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_engine():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from app.storage import SQLiteEngine
        db_path = os.path.join(tmpdir, "test.db")
        engine = SQLiteEngine(db_path)
        await engine.start()
        yield engine
        await engine.stop()


@pytest.fixture
async def plugin_context(db_engine):
    """Create a plugin context for testing"""
    from app.plugin import PluginContext
    ctx = PluginContext(engine=db_engine, config={})
    yield ctx


@pytest.fixture
async def plugin_manager(db_engine):
    """Create a plugin manager for testing"""
    from app.plugin import PluginManager
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = PluginManager(db_engine, tmpdir)
        yield manager
