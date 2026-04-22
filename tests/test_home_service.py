"""
HomeService 单元测试

测试首页数据聚合服务的各个方法：
- get_feed(): 聚合 blog + microblog + notes
- get_stats(): 获取统计数字
- get_active_authors(): 获取活跃作者
- get_home_data(): 并行查询全部数据
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.home_service import HomeService, HomeFeedItem, HomeStats, ActiveAuthor


# ============ Helper Functions ============

def make_blog_plugin(posts=None):
    """创建 mock blog plugin"""
    plugin = MagicMock()
    plugin.list_posts = AsyncMock(return_value=posts or [])
    return plugin


def make_microblog_plugin(posts=None):
    """创建 mock microblog plugin"""
    plugin = MagicMock()
    plugin.list_posts = AsyncMock(return_value=posts or [])
    return plugin


def make_notes_plugin(notes=None):
    """创建 mock notes plugin"""
    plugin = MagicMock()
    plugin.list_notes = AsyncMock(return_value=notes or [])
    return plugin


def make_board_plugin(stats=None, authors=None):
    """创建 mock board plugin"""
    plugin = MagicMock()
    plugin.get_stats = AsyncMock(return_value=stats or {"blog_count": 0, "microblog_count": 0, "note_count": 0})
    plugin.get_active_authors = AsyncMock(return_value=authors or [])
    return plugin


def make_plugin_manager(blog=None, microblog=None, notes=None, board=None):
    """创建 mock plugin_manager"""
    manager = MagicMock()
    manager.plugins = {}
    if blog:
        manager.plugins["blog"] = blog
    if microblog:
        manager.plugins["microblog"] = microblog
    if notes:
        manager.plugins["notes"] = notes
    if board:
        manager.plugins["board"] = board
    return manager


# ============ Test HomeFeedItem ============

class TestHomeFeedItem:
    """测试 HomeFeedItem dataclass"""

    def test_to_dict_post(self):
        """测试 post 类型转换"""
        item = HomeFeedItem(
            type="post",
            id=1,
            title="Test Title",
            body="Test Body",
            author_name="Alice",
            author_avatar="https://example.com/avatar.png",
            created_at=1700000000,
            tags=["tag1", "tag2"],
        )
        result = item.to_dict()
        assert result["type"] == "post"
        assert result["id"] == 1
        assert result["title"] == "Test Title"
        assert result["body"] == "Test Body"
        assert result["author_name"] == "Alice"
        assert result["tags"] == ["tag1", "tag2"]

    def test_to_dict_microblog(self):
        """测试 microblog 类型转换"""
        item = HomeFeedItem(
            type="microblog",
            id=2,
            title=None,
            body="Microblog content",
            author_name="Bob",
            author_avatar=None,
            created_at=1700001000,
        )
        result = item.to_dict()
        assert result["type"] == "microblog"
        assert result["title"] is None
        assert result["body"] == "Microblog content"

    def test_to_dict_note(self):
        """测试 note 类型转换"""
        item = HomeFeedItem(
            type="note",
            id=3,
            title="Note Title",
            body="Note Body",
            author_name="Charlie",
            author_avatar=None,
            created_at=1700002000,
        )
        result = item.to_dict()
        assert result["type"] == "note"
        assert result["title"] == "Note Title"


# ============ Test get_feed ============

class TestGetFeed:
    """测试 get_feed 方法"""

    @pytest.mark.asyncio
    async def test_empty_plugins(self):
        """测试无插件时返回空列表"""
        manager = make_plugin_manager()
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)
        assert feed == []

    @pytest.mark.asyncio
    async def test_blog_only(self):
        """测试仅 blog 插件"""
        blog = make_blog_plugin([
            {"id": 1, "title": "Post 1", "body": "Body 1", "author_name": "Alice", "created_at": 1000}
        ])
        manager = make_plugin_manager(blog=blog)
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)

        assert len(feed) == 1
        assert feed[0]["type"] == "post"
        assert feed[0]["title"] == "Post 1"
        assert feed[0]["author_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_microblog_only(self):
        """测试仅 microblog 插件"""
        microblog = make_microblog_plugin([
            {"id": 2, "content": "Micro 1", "author_name": "Bob", "created_at": 2000}
        ])
        manager = make_plugin_manager(microblog=microblog)
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)

        assert len(feed) == 1
        assert feed[0]["type"] == "microblog"
        assert feed[0]["body"] == "Micro 1"

    @pytest.mark.asyncio
    async def test_notes_only(self):
        """测试仅 notes 插件"""
        notes = make_notes_plugin([
            {"id": 3, "title": "Note 1", "body": "Note Body", "author_name": "Charlie", "created_at": 3000}
        ])
        manager = make_plugin_manager(notes=notes)
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)

        assert len(feed) == 1
        assert feed[0]["type"] == "note"

    @pytest.mark.asyncio
    async def test_mixed_feed_sorted_by_time(self):
        """测试混合内容按时间倒序排列"""
        blog = make_blog_plugin([
            {"id": 1, "title": "Post", "body": "B1", "author_name": "A", "created_at": 1000}
        ])
        microblog = make_microblog_plugin([
            {"id": 2, "content": "Micro", "author_name": "B", "created_at": 3000}
        ])
        notes = make_notes_plugin([
            {"id": 3, "title": "Note", "body": "N1", "author_name": "C", "created_at": 2000}
        ])
        manager = make_plugin_manager(blog=blog, microblog=microblog, notes=notes)
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)

        assert len(feed) == 3
        # 按时间倒序：microblog(3000) > note(2000) > post(1000)
        assert feed[0]["type"] == "microblog"
        assert feed[1]["type"] == "note"
        assert feed[2]["type"] == "post"

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        """测试 limit 参数生效"""
        blog = make_blog_plugin([
            {"id": i, "title": f"Post {i}", "body": f"B{i}", "author_name": "A", "created_at": i * 1000}
            for i in range(1, 20)
        ])
        manager = make_plugin_manager(blog=blog)
        service = HomeService(manager)
        feed = await service.get_feed(limit=5)

        assert len(feed) == 5

    @pytest.mark.asyncio
    async def test_plugin_exception_handled(self):
        """测试插件异常不影响其他插件"""
        blog = make_blog_plugin([
            {"id": 1, "title": "Post", "body": "B1", "author_name": "A", "created_at": 1000}
        ])
        # microblog 抛异常
        microblog = MagicMock()
        microblog.list_posts = AsyncMock(side_effect=Exception("DB error"))

        manager = make_plugin_manager(blog=blog, microblog=microblog)
        service = HomeService(manager)
        feed = await service.get_feed(limit=10)

        # blog 的数据仍然返回
        assert len(feed) == 1
        assert feed[0]["type"] == "post"


# ============ Test get_stats ============

class TestGetStats:
    """测试 get_stats 方法"""

    @pytest.mark.asyncio
    async def test_no_board_plugin(self):
        """测试无 board 插件返回默认值"""
        manager = make_plugin_manager()
        service = HomeService(manager)
        stats = await service.get_stats()

        assert stats.blog_count == 0
        assert stats.microblog_count == 0
        assert stats.note_count == 0

    @pytest.mark.asyncio
    async def test_board_plugin_returns_stats(self):
        """测试 board 插件返回统计"""
        board = make_board_plugin(stats={
            "blog_count": 10,
            "microblog_count": 20,
            "note_count": 30
        })
        manager = make_plugin_manager(board=board)
        service = HomeService(manager)
        stats = await service.get_stats()

        assert stats.blog_count == 10
        assert stats.microblog_count == 20
        assert stats.note_count == 30

    @pytest.mark.asyncio
    async def test_board_plugin_exception(self):
        """测试 board 插件异常返回默认值"""
        board = MagicMock()
        board.get_stats = AsyncMock(side_effect=Exception("DB error"))

        manager = make_plugin_manager(board=board)
        service = HomeService(manager)
        stats = await service.get_stats()

        assert stats.blog_count == 0
        assert stats.microblog_count == 0
        assert stats.note_count == 0


# ============ Test get_active_authors ============

class TestGetActiveAuthors:
    """测试 get_active_authors 方法"""

    @pytest.mark.asyncio
    async def test_no_board_plugin(self):
        """测试无 board 插件返回空列表"""
        manager = make_plugin_manager()
        service = HomeService(manager)
        authors = await service.get_active_authors()
        assert authors == []

    @pytest.mark.asyncio
    async def test_board_plugin_returns_authors(self):
        """测试 board 插件返回活跃作者"""
        board = make_board_plugin(authors=[
            {"name": "Alice", "count": 10},
            {"name": "Bob", "count": 5},
        ])
        manager = make_plugin_manager(board=board)
        service = HomeService(manager)
        authors = await service.get_active_authors()

        assert len(authors) == 2
        assert authors[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_board_plugin_exception(self):
        """测试 board 插件异常返回空列表"""
        board = MagicMock()
        board.get_active_authors = AsyncMock(side_effect=Exception("DB error"))

        manager = make_plugin_manager(board=board)
        service = HomeService(manager)
        authors = await service.get_active_authors()

        assert authors == []


# ============ Test get_home_data ============

class TestGetHomeData:
    """测试 get_home_data 并行查询"""

    @pytest.mark.asyncio
    async def test_all_empty(self):
        """测试全部为空"""
        manager = make_plugin_manager()
        service = HomeService(manager)
        data = await service.get_home_data()

        assert data["posts"] == []
        assert data["blog_count"] == 0
        assert data["microblog_count"] == 0
        assert data["note_count"] == 0
        assert data["active_authors"] == []

    @pytest.mark.asyncio
    async def test_all_data_combined(self):
        """测试全部数据组合"""
        blog = make_blog_plugin([
            {"id": 1, "title": "Post", "body": "B1", "author_name": "Alice", "created_at": 1000}
        ])
        board = make_board_plugin(
            stats={"blog_count": 5, "microblog_count": 10, "note_count": 15},
            authors=[{"name": "Alice", "count": 3}]
        )
        manager = make_plugin_manager(blog=blog, board=board)
        service = HomeService(manager)
        data = await service.get_home_data()

        assert len(data["posts"]) == 1
        assert data["blog_count"] == 5
        assert data["microblog_count"] == 10
        assert data["note_count"] == 15
        assert len(data["active_authors"]) == 1

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """测试并行执行（通过调用次数验证）"""
        blog = make_blog_plugin([
            {"id": 1, "title": "P1", "body": "B1", "author_name": "A", "created_at": 1000}
        ])
        board = make_board_plugin(
            stats={"blog_count": 1, "microblog_count": 0, "note_count": 0},
            authors=[{"name": "A", "count": 1}]
        )
        manager = make_plugin_manager(blog=blog, board=board)
        service = HomeService(manager)
        await service.get_home_data()

        # 验证各方法被调用
        blog.list_posts.assert_called_once()
        board.get_stats.assert_called_once()
        board.get_active_authors.assert_called_once()
