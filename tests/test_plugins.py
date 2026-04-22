"""Plugin CRUD tests for pyWork

Tests cover:
- Blog plugin: create/read/update/delete/search
- Notes plugin: create/read/update/delete
- Microblog plugin: create/read/delete
- Common patterns: pagination, filtering, error handling
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List, Optional
import json
import time


# ============================================================
#  Mock Engine (in-memory SQLite simulation)
# ============================================================

class MockEngine:
    """In-memory mock engine for testing"""
    
    def __init__(self):
        self.tables: Dict[str, Dict[int, Dict]] = {}
        self._next_id: Dict[str, int] = {}
    
    def _ensure_table(self, table: str):
        if table not in self.tables:
            self.tables[table] = {}
            self._next_id[table] = 1
    
    async def get(self, table: str, id: int) -> Optional[Dict]:
        self._ensure_table(table)
        return self.tables[table].get(id)
    
    async def put(self, table: str, id: int, data: Dict) -> None:
        self._ensure_table(table)
        self.tables[table][id] = data.copy()
    
    async def delete(self, table: str, id: int) -> None:
        self._ensure_table(table)
        self.tables[table].pop(id, None)
    
    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """Simple SQL simulation for common patterns"""
        # Handle SELECT ... FROM table WHERE id = ?
        if "blog_posts" in sql and "id" in sql.lower():
            if params:
                return self.tables.get("blog_posts", {}).get(params[0])
        if "notes" in sql and "id" in sql.lower():
            if params:
                return self.tables.get("notes", {}).get(params[0])
        return None
    
    async def fetchall(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Return all rows from table"""
        # Check for microblog_posts first (more specific)
        if "microblog_posts" in sql:
            return list(self.tables.get("microblog_posts", {}).values())
        if "blog_posts" in sql:
            return list(self.tables.get("blog_posts", {}).values())
        if "notes" in sql:
            return list(self.tables.get("notes", {}).values())
        return []


# ============================================================
#  Mock Plugin Implementations
# ============================================================

class MockBlogPlugin:
    """Mock blog plugin with CRUD operations"""
    
    def __init__(self, engine: MockEngine):
        self.engine = engine
        self.name = "blog"
    
    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        tags: Optional[List[str]] = None,
        author_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a blog post"""
        now = int(time.time())
        post = {
            "title": title,
            "body": content,
            "status": status,
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "author_id": author_id,
            "created_at": now,
            "updated_at": now
        }
        
        # Get next ID
        self.engine._ensure_table("blog_posts")
        post_id = len(self.engine.tables["blog_posts"]) + 1
        await self.engine.put("blog_posts", post_id, post)
        
        return {"id": post_id, "created": True}
    
    async def get_post(self, id: int) -> Optional[Dict[str, Any]]:
        """Get a blog post by ID"""
        post = await self.engine.get("blog_posts", id)
        if post and post.get("tags"):
            try:
                post["tags"] = json.loads(post["tags"])
            except:
                pass
        return post
    
    async def update_post(
        self,
        id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update a blog post"""
        existing = await self.engine.get("blog_posts", id)
        if not existing:
            return {"error": "Post not found"}
        
        if title is not None:
            existing["title"] = title
        if content is not None:
            existing["body"] = content
        if status is not None:
            existing["status"] = status
        if tags is not None:
            existing["tags"] = json.dumps(tags, ensure_ascii=False)
        
        existing["updated_at"] = int(time.time())
        await self.engine.put("blog_posts", id, existing)
        
        return {"id": id, "updated": True}
    
    async def delete_post(self, id: int) -> Dict[str, Any]:
        """Delete a blog post"""
        await self.engine.delete("blog_posts", id)
        return {"id": id, "deleted": True}
    
    async def list_posts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List all posts"""
        posts = await self.engine.fetchall("SELECT * FROM blog_posts", ())
        for post in posts:
            if post.get("tags"):
                try:
                    post["tags"] = json.loads(post["tags"])
                except:
                    pass
        return posts[:limit]


class MockNotesPlugin:
    """Mock notes plugin with CRUD operations"""
    
    def __init__(self, engine: MockEngine):
        self.engine = engine
        self.name = "notes"
    
    async def create_note(
        self,
        title: str,
        content: str,
        user_id: int,
        is_public: bool = False
    ) -> Dict[str, Any]:
        """Create a note"""
        now = int(time.time())
        note = {
            "title": title,
            "content": content,
            "user_id": user_id,
            "is_public": is_public,
            "created_at": now,
            "updated_at": now
        }
        
        self.engine._ensure_table("notes")
        note_id = len(self.engine.tables["notes"]) + 1
        await self.engine.put("notes", note_id, note)
        
        return {"id": note_id, "created": True}
    
    async def get_note(self, id: int) -> Optional[Dict[str, Any]]:
        """Get a note by ID"""
        return await self.engine.get("notes", id)
    
    async def update_note(
        self,
        id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update a note"""
        existing = await self.engine.get("notes", id)
        if not existing:
            return {"error": "Note not found"}
        
        if title is not None:
            existing["title"] = title
        if content is not None:
            existing["content"] = content
        if is_public is not None:
            existing["is_public"] = is_public
        
        existing["updated_at"] = int(time.time())
        await self.engine.put("notes", id, existing)
        
        return {"id": id, "updated": True}
    
    async def delete_note(self, id: int) -> Dict[str, Any]:
        """Delete a note"""
        await self.engine.delete("notes", id)
        return {"id": id, "deleted": True}
    
    async def list_notes(self, user_id: Optional[int] = None, limit: int = 20) -> List[Dict]:
        """List notes, optionally filtered by user"""
        notes = await self.engine.fetchall("SELECT * FROM notes", ())
        if user_id:
            notes = [n for n in notes if n.get("user_id") == user_id]
        return notes[:limit]


class MockMicroblogPlugin:
    """Mock microblog plugin"""
    
    def __init__(self, engine: MockEngine):
        self.engine = engine
        self.name = "microblog"
    
    async def create_post(
        self,
        content: str,
        author_id: int
    ) -> Dict[str, Any]:
        """Create a microblog post"""
        now = int(time.time())
        post = {
            "content": content,
            "author_id": author_id,
            "created_at": now
        }
        
        self.engine._ensure_table("microblog_posts")
        post_id = len(self.engine.tables["microblog_posts"]) + 1
        await self.engine.put("microblog_posts", post_id, post)
        
        return {"id": post_id, "created": True}
    
    async def get_post(self, id: int) -> Optional[Dict[str, Any]]:
        """Get a microblog post"""
        return await self.engine.get("microblog_posts", id)
    
    async def delete_post(self, id: int) -> Dict[str, Any]:
        """Delete a microblog post"""
        await self.engine.delete("microblog_posts", id)
        return {"id": id, "deleted": True}
    
    async def list_posts(self, limit: int = 20) -> List[Dict]:
        """List microblog posts"""
        posts = await self.engine.fetchall("SELECT * FROM microblog_posts", ())
        return posts[:limit]


# ============================================================
#  Test Fixtures
# ============================================================

@pytest.fixture
def engine():
    return MockEngine()


@pytest.fixture
def blog_plugin(engine):
    return MockBlogPlugin(engine)


@pytest.fixture
def notes_plugin(engine):
    return MockNotesPlugin(engine)


@pytest.fixture
def microblog_plugin(engine):
    return MockMicroblogPlugin(engine)


# ============================================================
#  Blog Plugin Tests
# ============================================================

class TestBlogCreate:
    """Tests for blog post creation"""
    
    @pytest.mark.asyncio
    async def test_create_post_success(self, blog_plugin):
        """Create a blog post successfully"""
        result = await blog_plugin.create_post(
            title="Test Post",
            content="This is a test",
            status="draft"
        )
        
        assert result["created"] is True
        assert result["id"] == 1
    
    @pytest.mark.asyncio
    async def test_create_post_with_tags(self, blog_plugin):
        """Create a blog post with tags"""
        result = await blog_plugin.create_post(
            title="Tagged Post",
            content="Content",
            tags=["python", "testing"]
        )
        
        assert result["created"] is True
        
        # Verify tags stored correctly
        post = await blog_plugin.get_post(result["id"])
        assert "python" in post["tags"]
        assert "testing" in post["tags"]
    
    @pytest.mark.asyncio
    async def test_create_post_default_status(self, blog_plugin):
        """Create post without status should default to draft"""
        result = await blog_plugin.create_post(
            title="Default Status",
            content="Content"
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert post["status"] == "draft"
    
    @pytest.mark.asyncio
    async def test_create_post_published(self, blog_plugin):
        """Create a published post"""
        result = await blog_plugin.create_post(
            title="Published Post",
            content="Content",
            status="published"
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert post["status"] == "published"
    
    @pytest.mark.asyncio
    async def test_create_post_with_author(self, blog_plugin):
        """Create post with author_id"""
        result = await blog_plugin.create_post(
            title="Authored Post",
            content="Content",
            author_id=42
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert post["author_id"] == 42


class TestBlogRead:
    """Tests for blog post reading"""
    
    @pytest.mark.asyncio
    async def test_get_post_success(self, blog_plugin):
        """Get an existing post"""
        created = await blog_plugin.create_post(
            title="Test",
            content="Content"
        )
        
        post = await blog_plugin.get_post(created["id"])
        
        assert post is not None
        assert post["title"] == "Test"
        assert post["body"] == "Content"
    
    @pytest.mark.asyncio
    async def test_get_post_not_found(self, blog_plugin):
        """Get non-existent post returns None"""
        post = await blog_plugin.get_post(999)
        
        assert post is None
    
    @pytest.mark.asyncio
    async def test_list_posts_empty(self, blog_plugin):
        """List posts when empty"""
        posts = await blog_plugin.list_posts()
        
        assert posts == []
    
    @pytest.mark.asyncio
    async def test_list_posts_multiple(self, blog_plugin):
        """List multiple posts"""
        await blog_plugin.create_post("Post 1", "Content 1")
        await blog_plugin.create_post("Post 2", "Content 2")
        await blog_plugin.create_post("Post 3", "Content 3")
        
        posts = await blog_plugin.list_posts()
        
        assert len(posts) == 3
    
    @pytest.mark.asyncio
    async def test_list_posts_limit(self, blog_plugin):
        """List posts with limit"""
        for i in range(10):
            await blog_plugin.create_post(f"Post {i}", f"Content {i}")
        
        posts = await blog_plugin.list_posts(limit=5)
        
        assert len(posts) == 5


class TestBlogUpdate:
    """Tests for blog post update"""
    
    @pytest.mark.asyncio
    async def test_update_post_title(self, blog_plugin):
        """Update post title"""
        created = await blog_plugin.create_post("Original", "Content")
        
        result = await blog_plugin.update_post(
            id=created["id"],
            title="Updated Title"
        )
        
        assert result["updated"] is True
        
        post = await blog_plugin.get_post(created["id"])
        assert post["title"] == "Updated Title"
    
    @pytest.mark.asyncio
    async def test_update_post_content(self, blog_plugin):
        """Update post content"""
        created = await blog_plugin.create_post("Title", "Original content")
        
        await blog_plugin.update_post(
            id=created["id"],
            content="New content"
        )
        
        post = await blog_plugin.get_post(created["id"])
        assert post["body"] == "New content"
    
    @pytest.mark.asyncio
    async def test_update_post_status(self, blog_plugin):
        """Update post status"""
        created = await blog_plugin.create_post("Title", "Content", status="draft")
        
        await blog_plugin.update_post(
            id=created["id"],
            status="published"
        )
        
        post = await blog_plugin.get_post(created["id"])
        assert post["status"] == "published"
    
    @pytest.mark.asyncio
    async def test_update_post_tags(self, blog_plugin):
        """Update post tags"""
        created = await blog_plugin.create_post("Title", "Content")
        
        await blog_plugin.update_post(
            id=created["id"],
            tags=["new", "tags"]
        )
        
        post = await blog_plugin.get_post(created["id"])
        assert "new" in post["tags"]
        assert "tags" in post["tags"]
    
    @pytest.mark.asyncio
    async def test_update_post_not_found(self, blog_plugin):
        """Update non-existent post returns error"""
        result = await blog_plugin.update_post(
            id=999,
            title="New Title"
        )
        
        assert "error" in result
        assert result["error"] == "Post not found"
    
    @pytest.mark.asyncio
    async def test_update_post_partial(self, blog_plugin):
        """Partial update should preserve other fields"""
        created = await blog_plugin.create_post(
            "Original",
            "Original content",
            status="draft"
        )
        
        # Only update title
        await blog_plugin.update_post(
            id=created["id"],
            title="New Title"
        )
        
        post = await blog_plugin.get_post(created["id"])
        assert post["title"] == "New Title"
        assert post["body"] == "Original content"  # Preserved
        assert post["status"] == "draft"  # Preserved


class TestBlogDelete:
    """Tests for blog post deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_post_success(self, blog_plugin):
        """Delete an existing post"""
        created = await blog_plugin.create_post("To Delete", "Content")
        
        result = await blog_plugin.delete_post(created["id"])
        
        assert result["deleted"] is True
        
        # Verify deleted
        post = await blog_plugin.get_post(created["id"])
        assert post is None
    
    @pytest.mark.asyncio
    async def test_delete_post_not_found(self, blog_plugin):
        """Delete non-existent post should succeed (idempotent)"""
        result = await blog_plugin.delete_post(999)
        
        assert result["deleted"] is True


# ============================================================
#  Notes Plugin Tests
# ============================================================

class TestNotesCreate:
    """Tests for note creation"""
    
    @pytest.mark.asyncio
    async def test_create_note_success(self, notes_plugin):
        """Create a note successfully"""
        result = await notes_plugin.create_note(
            title="My Note",
            content="Note content",
            user_id=1
        )
        
        assert result["created"] is True
        assert result["id"] == 1
    
    @pytest.mark.asyncio
    async def test_create_note_private_by_default(self, notes_plugin):
        """Create note is private by default"""
        result = await notes_plugin.create_note(
            title="Private Note",
            content="Secret",
            user_id=1
        )
        
        note = await notes_plugin.get_note(result["id"])
        assert note["is_public"] is False
    
    @pytest.mark.asyncio
    async def test_create_note_public(self, notes_plugin):
        """Create a public note"""
        result = await notes_plugin.create_note(
            title="Public Note",
            content="Shared",
            user_id=1,
            is_public=True
        )
        
        note = await notes_plugin.get_note(result["id"])
        assert note["is_public"] is True


class TestNotesRead:
    """Tests for note reading"""
    
    @pytest.mark.asyncio
    async def test_get_note_success(self, notes_plugin):
        """Get an existing note"""
        created = await notes_plugin.create_note(
            "Test Note",
            "Content",
            user_id=1
        )
        
        note = await notes_plugin.get_note(created["id"])
        
        assert note is not None
        assert note["title"] == "Test Note"
    
    @pytest.mark.asyncio
    async def test_list_notes_by_user(self, notes_plugin):
        """List notes filtered by user"""
        await notes_plugin.create_note("Note 1", "Content", user_id=1)
        await notes_plugin.create_note("Note 2", "Content", user_id=2)
        await notes_plugin.create_note("Note 3", "Content", user_id=1)
        
        notes = await notes_plugin.list_notes(user_id=1)
        
        assert len(notes) == 2


class TestNotesUpdate:
    """Tests for note update"""
    
    @pytest.mark.asyncio
    async def test_update_note_title(self, notes_plugin):
        """Update note title"""
        created = await notes_plugin.create_note("Original", "Content", user_id=1)
        
        await notes_plugin.update_note(id=created["id"], title="Updated")
        
        note = await notes_plugin.get_note(created["id"])
        assert note["title"] == "Updated"
    
    @pytest.mark.asyncio
    async def test_update_note_visibility(self, notes_plugin):
        """Update note visibility"""
        created = await notes_plugin.create_note("Note", "Content", user_id=1)
        
        await notes_plugin.update_note(id=created["id"], is_public=True)
        
        note = await notes_plugin.get_note(created["id"])
        assert note["is_public"] is True


class TestNotesDelete:
    """Tests for note deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_note_success(self, notes_plugin):
        """Delete a note"""
        created = await notes_plugin.create_note("To Delete", "Content", user_id=1)
        
        result = await notes_plugin.delete_note(created["id"])
        
        assert result["deleted"] is True
        
        note = await notes_plugin.get_note(created["id"])
        assert note is None


# ============================================================
#  Microblog Plugin Tests
# ============================================================

class TestMicroblogCreate:
    """Tests for microblog post creation"""
    
    @pytest.mark.asyncio
    async def test_create_microblog_success(self, microblog_plugin):
        """Create a microblog post"""
        result = await microblog_plugin.create_post(
            content="Hello world!",
            author_id=1
        )
        
        assert result["created"] is True
    
    @pytest.mark.asyncio
    async def test_create_microblog_multiple(self, microblog_plugin):
        """Create multiple microblog posts"""
        r1 = await microblog_plugin.create_post("Post 1", author_id=1)
        r2 = await microblog_plugin.create_post("Post 2", author_id=1)
        
        assert r1["id"] == 1
        assert r2["id"] == 2


class TestMicroblogRead:
    """Tests for microblog reading"""
    
    @pytest.mark.asyncio
    async def test_get_microblog_success(self, microblog_plugin):
        """Get a microblog post"""
        created = await microblog_plugin.create_post("Hello", author_id=1)
        
        post = await microblog_plugin.get_post(created["id"])
        
        assert post is not None
        assert post["content"] == "Hello"
    
    @pytest.mark.asyncio
    async def test_list_microblog_posts(self, microblog_plugin):
        """List microblog posts"""
        await microblog_plugin.create_post("Post 1", author_id=1)
        await microblog_plugin.create_post("Post 2", author_id=2)
        
        posts = await microblog_plugin.list_posts()
        
        assert len(posts) == 2


class TestMicroblogDelete:
    """Tests for microblog deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_microblog_success(self, microblog_plugin):
        """Delete a microblog post"""
        created = await microblog_plugin.create_post("To delete", author_id=1)
        
        result = await microblog_plugin.delete_post(created["id"])
        
        assert result["deleted"] is True


# ============================================================
#  Cross-Plugin Tests
# ============================================================

class TestCrossPlugin:
    """Tests involving multiple plugins"""
    
    @pytest.mark.asyncio
    async def test_shared_engine(self, engine):
        """Multiple plugins can share the same engine"""
        blog = MockBlogPlugin(engine)
        notes = MockNotesPlugin(engine)
        
        # Create in both
        blog_result = await blog.create_post("Blog Post", "Content")
        note_result = await notes.create_note("Note", "Content", user_id=1)
        
        assert blog_result["created"] is True
        assert note_result["created"] is True
        
        # Verify isolation
        blog_post = await blog.get_post(blog_result["id"])
        note = await notes.get_note(note_result["id"])
        
        assert "body" in blog_post  # Blog has 'body'
        assert "content" in note    # Note has 'content'
    
    @pytest.mark.asyncio
    async def test_timestamps_updated(self, blog_plugin):
        """Updated_at should change on update"""
        created = await blog_plugin.create_post("Test", "Content")
        
        post1 = await blog_plugin.get_post(created["id"])
        original_updated = post1["updated_at"]
        
        # Wait a tiny bit (simulate time passing)
        import asyncio
        await asyncio.sleep(0.01)
        
        await blog_plugin.update_post(created["id"], title="Updated")
        
        post2 = await blog_plugin.get_post(created["id"])
        assert post2["updated_at"] >= original_updated


# ============================================================
#  Edge Cases
# ============================================================

class TestEdgeCases:
    """Edge case tests"""
    
    @pytest.mark.asyncio
    async def test_empty_content(self, blog_plugin):
        """Create post with empty content"""
        result = await blog_plugin.create_post("Empty Post", "")
        
        post = await blog_plugin.get_post(result["id"])
        assert post["body"] == ""
    
    @pytest.mark.asyncio
    async def test_special_characters_in_title(self, blog_plugin):
        """Create post with special characters"""
        result = await blog_plugin.create_post(
            "Test <script>alert('xss')</script>",
            "Content"
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert "<script>" in post["title"]  # Stored as-is
    
    @pytest.mark.asyncio
    async def test_unicode_content(self, blog_plugin):
        """Create post with unicode content"""
        result = await blog_plugin.create_post(
            "中文标题",
            "内容测试 🎉"
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert post["title"] == "中文标题"
        assert "🎉" in post["body"]
    
    @pytest.mark.asyncio
    async def test_long_content(self, blog_plugin):
        """Create post with very long content"""
        long_content = "x" * 10000
        
        result = await blog_plugin.create_post("Long Post", long_content)
        
        post = await blog_plugin.get_post(result["id"])
        assert len(post["body"]) == 10000
    
    @pytest.mark.asyncio
    async def test_empty_tags(self, blog_plugin):
        """Create post with empty tags list"""
        result = await blog_plugin.create_post(
            "No Tags",
            "Content",
            tags=[]
        )
        
        post = await blog_plugin.get_post(result["id"])
        assert post["tags"] == []
