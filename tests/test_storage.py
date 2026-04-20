"""Tests for storage engine"""
import pytest
import asyncio
import os
import tempfile

from app.storage import SQLiteEngine, RaftIndex


@pytest.fixture
async def engine():
    """Create a test engine"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = SQLiteEngine(db_path)
        await engine.start()
        yield engine
        await engine.stop()


@pytest.mark.asyncio
async def test_engine_start_stop(engine):
    """Test engine can start and stop"""
    assert engine.mode == "sqlite"


@pytest.mark.asyncio
async def test_put_and_get(engine):
    """Test basic put and get on blog_posts"""
    await engine.put("blog_posts", 0, {
        "author_id": 1,
        "title": "Test Post",
        "body": "This is a test",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    result = await engine.fetchone(
        "SELECT * FROM blog_posts WHERE title = ?", ("Test Post",)
    )
    
    assert result is not None
    assert result["title"] == "Test Post"
    assert result["body"] == "This is a test"


@pytest.mark.asyncio
async def test_query(engine):
    """Test query with filters"""
    for i in range(5):
        await engine.put("blog_posts", 0, {
            "author_id": 1,
            "title": f"Post {i}",
            "body": f"Content {i}",
            "status": "published" if i % 2 == 0 else "draft",
            "created_at": 1234567890 + i,
            "updated_at": 1234567890 + i
        })
    
    results = await engine.query("blog_posts", status="published")
    assert len(results) >= 3


@pytest.mark.asyncio
async def test_delete(engine):
    """Test delete"""
    await engine.put("blog_posts", 0, {
        "author_id": 1,
        "title": "To Delete",
        "body": "Will be deleted",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    result = await engine.fetchone(
        "SELECT id FROM blog_posts WHERE title = ?", ("To Delete",)
    )
    assert result is not None
    post_id = result["id"]
    
    await engine.delete("blog_posts", post_id)
    
    result = await engine.get("blog_posts", post_id)
    assert result is None


@pytest.mark.asyncio
async def test_raft_log(engine):
    """Test raft log is being written"""
    await engine.put("blog_posts", 0, {
        "author_id": 1,
        "title": "Logged Post",
        "body": "This should be logged",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    logs = await engine.export(RaftIndex(term=0, index=0))
    assert len(logs) > 0
    
    last_log = logs[-1]
    assert last_log.table == "blog_posts"
    assert last_log.op in ("INSERT", "UPDATE")


@pytest.mark.asyncio
async def test_export_import(engine):
    """Test export and import for migration"""
    await engine.put("blog_posts", 0, {
        "author_id": 1,
        "title": "Export Test",
        "body": "Testing export",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    logs = await engine.export(RaftIndex(term=0, index=0))
    assert len(logs) > 0
    
    current = engine.current_index()
    assert current.index > 0


@pytest.mark.asyncio
async def test_microblog_posts_table(engine):
    """Test microblog_posts table with content field"""
    await engine.put("microblog_posts", 0, {
        "author_id": 1,
        "content": "Hello world",
        "visibility": "public",
        "status": "public",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    result = await engine.fetchone("SELECT * FROM microblog_posts WHERE content = ?", ("Hello world",))
    assert result is not None
    assert result["content"] == "Hello world"


@pytest.mark.asyncio
async def test_notes_table(engine):
    """Test notes table"""
    await engine.put("notes", 0, {
        "author_id": 1,
        "title": "My Note",
        "body": "Note content",
        "visibility": "private",
        "status": "published",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    result = await engine.fetchone("SELECT * FROM notes WHERE title = ?", ("My Note",))
    assert result is not None
    assert result["body"] == "Note content"


@pytest.mark.asyncio
async def test_guestbook_entries_table(engine):
    """Test guestbook_entries table with dedicated fields"""
    await engine.put("guestbook_entries", 0, {
        "nickname": "Visitor",
        "body": "Nice site!",
        "email": "test@example.com",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    result = await engine.fetchone("SELECT * FROM guestbook_entries WHERE nickname = ?", ("Visitor",))
    assert result is not None
    assert result["body"] == "Nice site!"
    assert result["email"] == "test@example.com"
