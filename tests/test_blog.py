"""Tests for blog plugin"""
import pytest
import os
import tempfile

from app.storage import SQLiteEngine
from app.plugin import PluginContext, PluginManager
from plugins.blog import BlogPlugin


@pytest.fixture
async def setup_blog():
    """Setup blog plugin for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = SQLiteEngine(db_path)
        await engine.start()
        
        ctx = PluginContext(engine=engine, config={})
        plugin = BlogPlugin()
        await plugin.init(ctx)
        
        yield plugin, engine
        
        await engine.stop()


@pytest.mark.asyncio
async def test_create_post(setup_blog):
    """Test creating a blog post"""
    plugin, engine = setup_blog
    
    result = await plugin.create_post(
        title="Test Post",
        content="This is a test post content",
        status="draft",
        tags=["test", "blog"]
    )
    
    assert result["id"] > 0
    assert result["title"] == "Test Post"
    assert result["status"] == "draft"


@pytest.mark.asyncio
async def test_search_posts(setup_blog):
    """Test searching posts"""
    plugin, engine = setup_blog
    
    # Create multiple posts
    await plugin.create_post(title="Python Tips", content="Python content", status="published")
    await plugin.create_post(title="Go Tips", content="Go content", status="published")
    await plugin.create_post(title="Draft Post", content="Draft content", status="draft")
    
    # Search all
    results = await plugin.search_posts(limit=10)
    assert len(results) >= 3
    
    # Search published only
    published = await plugin.search_posts(status="published")
    assert len(published) >= 2


@pytest.mark.asyncio
async def test_update_post(setup_blog):
    """Test updating a post"""
    plugin, engine = setup_blog
    
    # Create
    result = await plugin.create_post(title="Original", content="Original content")
    post_id = result["id"]
    
    # Update
    updated = await plugin.update_post(id=post_id, title="Updated", status="published")
    
    # Verify
    post = await engine.get("blog_posts", post_id)
    assert post["title"] == "Updated"
    assert post["status"] == "published"


@pytest.mark.asyncio
async def test_mcp_tools(setup_blog):
    """Test MCP tools are registered"""
    plugin, engine = setup_blog
    
    tools = plugin.mcp_tools()
    assert len(tools) > 0
    
    tool_names = [t.name for t in tools]
    assert "create_post" in tool_names
    assert "search_posts" in tool_names
    assert "update_post" in tool_names


@pytest.mark.asyncio
async def test_mcp_resources(setup_blog):
    """Test MCP resources"""
    plugin, engine = setup_blog
    
    # Create a post
    await plugin.create_post(title="Resource Test", content="Resource content")
    
    # Get resource
    resource_content = await plugin.list_all_posts()
    assert "Resource Test" in resource_content


@pytest.mark.asyncio
async def test_plugin_manager(setup_blog):
    """Test plugin manager integration"""
    plugin, engine = setup_blog
    
    # Create a plugin manager
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = PluginManager(engine, tmpdir)
        
        # Register plugin manually
        manager.plugins["blog"] = plugin
        manager.contexts["blog"] = PluginContext(engine=engine, config={})
        
        # Get all tools
        tools = manager.get_all_tools()
        assert len(tools) > 0
        
        # Find create_post tool
        create_tool = None
        for _, tool in tools:
            if tool.name == "create_post":
                create_tool = tool
                break
        
        assert create_tool is not None
        assert create_tool.description == "Create a blog post"
