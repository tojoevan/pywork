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

        # Add nickname/display_name columns (normally added by auth plugin migration)
        try:
            await engine.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            await engine.execute("ALTER TABLE users ADD COLUMN display_name TEXT DEFAULT ''")
        except Exception:
            pass

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
        tags=["test", "blog"],
        author_id=1
    )
    
    assert result["id"] > 0
    assert result["title"] == "Test Post"
    assert result["status"] == "draft"


@pytest.mark.asyncio
async def test_create_post_default_status(setup_blog):
    """Test creating a blog post without status defaults to published"""
    plugin, engine = setup_blog
    
    result = await plugin.create_post(
        title="Test Default Status Post",
        content="This is a test post content",
        tags=["test", "blog"],
        author_id=1
    )
    
    assert result["id"] > 0
    assert result["title"] == "Test Default Status Post"
    assert result["status"] == "published"


@pytest.mark.asyncio
async def test_search_posts(setup_blog):
    """Test searching posts"""
    plugin, engine = setup_blog
    
    # Create multiple posts
    await plugin.create_post(title="Python Tips", content="Python content", status="published", author_id=1)
    await plugin.create_post(title="Go Tips", content="Go content", status="published", author_id=1)
    await plugin.create_post(title="Draft Post", content="Draft content", status="draft", author_id=1)
    
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
    result = await plugin.create_post(title="Original", content="Original content", author_id=1)
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
    await plugin.create_post(title="Resource Test", content="Resource content", author_id=1)
    
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


# ============================================================
#  搜索与过滤测试
# ============================================================

@pytest.mark.asyncio
async def test_search_empty_query(setup_blog):
    """搜索空关键词应返回所有文章"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Post A", content="Content A", status="published", author_id=1)
    await plugin.create_post(title="Post B", content="Content B", status="draft", author_id=1)

    results = await plugin.search_posts(query=None, limit=100)
    assert len(results) >= 2


@pytest.mark.asyncio
async def test_search_by_tag(setup_blog):
    """按标签过滤文章"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Python Post", content="Content", tags=["python", "tutorial"], author_id=1)
    await plugin.create_post(title="Go Post", content="Content", tags=["go"], author_id=1)
    await plugin.create_post(title="No Tag Post", content="Content", author_id=1)

    # 按 python 标签过滤
    results = await plugin.search_posts(tag="python")
    assert len(results) >= 1
    assert all("python" in (r.get("tags") or []) for r in results)

    # 按不存在的标签过滤
    results = await plugin.search_posts(tag="nonexistent")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_status_filter(setup_blog):
    """按状态过滤文章"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Draft", content="Content", status="draft", author_id=1)
    await plugin.create_post(title="Published", content="Content", status="published", author_id=1)
    await plugin.create_post(title="Archived", content="Content", status="archived", author_id=1)

    drafts = await plugin.search_posts(status="draft")
    assert all(r["status"] == "draft" for r in drafts)

    published = await plugin.search_posts(status="published")
    assert all(r["status"] == "published" for r in published)

    archived = await plugin.search_posts(status="archived")
    assert all(r["status"] == "archived" for r in archived)


@pytest.mark.asyncio
async def test_search_combined_filters(setup_blog):
    """组合过滤：状态 + 标签"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Py Published", content="Content", status="published", tags=["python"], author_id=1)
    await plugin.create_post(title="Py Draft", content="Content", status="draft", tags=["python"], author_id=1)
    await plugin.create_post(title="Go Published", content="Content", status="published", tags=["go"], author_id=1)

    results = await plugin.search_posts(tag="python", status="published")
    assert len(results) >= 1
    for r in results:
        assert r["status"] == "published"
        assert "python" in (r.get("tags") or [])


@pytest.mark.asyncio
async def test_search_pagination(setup_blog):
    """分页测试"""
    plugin, engine = setup_blog
    for i in range(10):
        await plugin.create_post(title=f"Post {i}", content=f"Content {i}", status="published", author_id=1)

    # 第一页
    page1 = await plugin.search_posts(limit=3, offset=0)
    assert len(page1) == 3

    # 第二页
    page2 = await plugin.search_posts(limit=3, offset=3)
    assert len(page2) == 3

    # 确保不重复
    page1_ids = {r["id"] for r in page1}
    page2_ids = {r["id"] for r in page2}
    assert page1_ids.isdisjoint(page2_ids)

    # 超出范围
    page_overflow = await plugin.search_posts(limit=10, offset=100)
    assert len(page_overflow) == 0


@pytest.mark.asyncio
async def test_search_by_author(setup_blog):
    """按作者过滤"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Author 1 Post", content="Content", author_id=1)
    await plugin.create_post(title="Author 2 Post", content="Content", author_id=2)

    results = await plugin.search_posts(author_id=1)
    assert all(r["author_id"] == 1 for r in results)

    results = await plugin.search_posts(author_id=2)
    assert all(r["author_id"] == 2 for r in results)


# ============================================================
#  文章操作测试
# ============================================================

@pytest.mark.asyncio
async def test_delete_post(setup_blog):
    """删除文章"""
    plugin, engine = setup_blog
    result = await plugin.create_post(title="To Delete", content="Content", author_id=1)
    post_id = result["id"]

    deleted = await plugin.delete_post_mcp(id=post_id)
    assert deleted.get("deleted") is True

    # 确认已删除
    post = await engine.get("blog_posts", post_id)
    assert post is None


@pytest.mark.asyncio
async def test_delete_nonexistent_post(setup_blog):
    """删除不存在的文章（SQLite DELETE 是 no-op，返回 success）"""
    plugin, engine = setup_blog
    result = await plugin.delete_post_mcp(id=99999)
    # delete_post_mcp 不检查存在性，DELETE 是幂等操作
    assert result.get("deleted") is True


@pytest.mark.asyncio
async def test_update_post_fields(setup_blog):
    """更新文章各字段"""
    plugin, engine = setup_blog
    result = await plugin.create_post(title="Original", content="Original content", tags=["old"], author_id=1)
    post_id = result["id"]

    # 更新标题
    await plugin.update_post(id=post_id, title="Updated Title")
    post = await engine.get("blog_posts", post_id)
    assert post["title"] == "Updated Title"

    # 更新内容
    await plugin.update_post(id=post_id, content="New body")
    post = await engine.get("blog_posts", post_id)
    assert post["body"] == "New body"

    # 更新状态
    await plugin.update_post(id=post_id, status="archived")
    post = await engine.get("blog_posts", post_id)
    assert post["status"] == "archived"


@pytest.mark.asyncio
async def test_count_posts(setup_blog):
    """计数功能"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Pub 1", content="Content", status="published", author_id=1)
    await plugin.create_post(title="Pub 2", content="Content", status="published", author_id=1)
    await plugin.create_post(title="Draft 1", content="Content", status="draft", author_id=1)

    total = await plugin.count_posts()
    assert total >= 3

    published = await plugin.count_posts(status="published")
    assert published >= 2

    draft = await plugin.count_posts(status="draft")
    assert draft >= 1


@pytest.mark.asyncio
async def test_create_post_without_author(setup_blog):
    """无作者创建文章应失败"""
    plugin, engine = setup_blog
    result = await plugin.create_post(title="No Author", content="Content", author_id=None)
    assert result.get("error") is not None


@pytest.mark.asyncio
async def test_create_post_empty_title(setup_blog):
    """空标题创建文章"""
    plugin, engine = setup_blog
    # 空标题应该能创建（数据库允许）
    result = await plugin.create_post(title="", content="Content", author_id=1)
    assert result.get("id") is not None


@pytest.mark.asyncio
async def test_list_all_posts_resource(setup_blog):
    """list_all_posts 资源格式"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Resource Post", content="Hello World", author_id=1)

    resource = await plugin.list_all_posts()
    assert "Resource Post" in resource
    assert "Hello World" in resource


@pytest.mark.asyncio
async def test_get_post_resource(setup_blog):
    """get_post_resource 单篇资源"""
    plugin, engine = setup_blog
    result = await plugin.create_post(title="Single Post", content="Detailed content", author_id=1)
    post_id = result["id"]

    resource = await plugin.get_post_resource(post_id)
    assert "Single Post" in resource
    assert "Detailed content" in resource


@pytest.mark.asyncio
async def test_get_post_resource_not_found(setup_blog):
    """获取不存在文章的资源"""
    plugin, engine = setup_blog
    resource = await plugin.get_post_resource(99999)
    assert "not found" in resource.lower()


@pytest.mark.asyncio
async def test_search_posts_fts(setup_blog):
    """全文搜索（FTS5）"""
    plugin, engine = setup_blog
    await plugin.create_post(title="Python Tutorial", content="Learn Python basics", author_id=1)
    await plugin.create_post(title="Go Guide", content="Learn Go concurrency", author_id=1)
    await plugin.create_post(title="Rust Intro", content="Rust ownership model", author_id=1)

    # 直接查询 FTS 表验证索引正确
    fts_count = await engine.fetchone("SELECT COUNT(*) as cnt FROM blog_posts_fts")
    assert fts_count["cnt"] >= 3

    # 通过 FTS 搜索
    fts_results = await engine.fetchall(
        "SELECT rowid FROM blog_posts_fts WHERE blog_posts_fts MATCH ?", ("Python",)
    )
    assert len(fts_results) >= 1


@pytest.mark.asyncio
async def test_mcp_call_create(setup_blog):
    """MCP 调用创建文章"""
    plugin, engine = setup_blog
    result = await plugin.mcp_call("create_post", {"title": "MCP Post", "content": "Via MCP"}, mcp_token=None)
    # 无 token 且无 author_id 应该失败
    assert result.get("error") is not None


@pytest.mark.asyncio
async def test_mcp_call_unknown_tool(setup_blog):
    """MCP 调用未知工具"""
    plugin, engine = setup_blog
    with pytest.raises(ValueError, match="Unknown tool"):
        await plugin.mcp_call("nonexistent_tool", {})
