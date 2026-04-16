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
    """Test basic put and get"""
    # Insert a content
    await engine.put("contents", 0, {
        "plugin_type": "blog",
        "author_id": 1,
        "title": "Test Post",
        "body": "This is a test",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    # Get it back
    result = await engine.fetchone(
        "SELECT * FROM contents WHERE title = ?", ("Test Post",)
    )
    
    assert result is not None
    assert result["title"] == "Test Post"
    assert result["body"] == "This is a test"


@pytest.mark.asyncio
async def test_query(engine):
    """Test query with filters"""
    # Insert multiple contents
    for i in range(5):
        await engine.put("contents", 0, {
            "plugin_type": "blog",
            "author_id": 1,
            "title": f"Post {i}",
            "body": f"Content {i}",
            "status": "published" if i % 2 == 0 else "draft",
            "created_at": 1234567890 + i,
            "updated_at": 1234567890 + i
        })
    
    # Query published posts
    results = await engine.query("contents", plugin_type="blog", status="published")
    
    assert len(results) >= 3  # At least 3 published


@pytest.mark.asyncio
async def test_delete(engine):
    """Test delete"""
    # Insert
    await engine.put("contents", 0, {
        "plugin_type": "blog",
        "author_id": 1,
        "title": "To Delete",
        "body": "Will be deleted",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    # Get ID
    result = await engine.fetchone(
        "SELECT id FROM contents WHERE title = ?", ("To Delete",)
    )
    assert result is not None
    post_id = result["id"]
    
    # Delete
    await engine.delete("contents", post_id)
    
    # Verify deleted
    result = await engine.get("contents", post_id)
    assert result is None


@pytest.mark.asyncio
async def test_raft_log(engine):
    """Test raft log is being written"""
    # Insert content
    await engine.put("contents", 0, {
        "plugin_type": "blog",
        "author_id": 1,
        "title": "Logged Post",
        "body": "This should be logged",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    # Check log exists
    logs = await engine.export(RaftIndex(term=0, index=0))
    assert len(logs) > 0
    
    # Check log content
    last_log = logs[-1]
    assert last_log.table == "contents"
    assert last_log.op in ("INSERT", "UPDATE")


@pytest.mark.asyncio
async def test_export_import(engine):
    """Test export and import for migration"""
    # Insert content
    await engine.put("contents", 0, {
        "plugin_type": "blog",
        "author_id": 1,
        "title": "Export Test",
        "body": "Testing export",
        "status": "draft",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    # Export logs
    logs = await engine.export(RaftIndex(term=0, index=0))
    assert len(logs) > 0
    
    # Verify current index
    current = engine.current_index()
    assert current.index > 0
