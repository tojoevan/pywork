"""首页数据聚合服务"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import asyncio

from app.log import get_logger

log = get_logger(__name__, "services")


@dataclass
class HomeFeedItem:
    """首页流条目统一格式"""
    type: str           # "post" | "microblog" | "note"
    id: int
    title: Optional[str]
    body: str
    author_name: str
    author_avatar: Optional[str]
    created_at: int
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为模板可用的 dict"""
        d = {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "author_name": self.author_name,
            "author_avatar": self.author_avatar,
            "created_at": self.created_at,
        }
        if self.tags:
            d["tags"] = self.tags
        return d


@dataclass
class HomeStats:
    """首页统计"""
    blog_count: int = 0
    microblog_count: int = 0
    note_count: int = 0

    @property
    def total_count(self) -> int:
        return self.blog_count + self.microblog_count + self.note_count


@dataclass
class ActiveAuthor:
    """活跃作者"""
    author_name: str
    author_avatar: Optional[str]
    blog_count: int
    microblog_count: int
    note_count: int


class HomeService:
    """首页数据聚合服务"""

    def __init__(self, plugin_manager):
        self._plugins = plugin_manager.plugins

    def _get_plugin(self, name: str):
        """安全获取插件"""
        return self._plugins.get(name)

    # ========================================================
    #  数据转换
    # ========================================================

    def _transform_blog_post(self, post: Dict) -> HomeFeedItem:
        """转换博客文章"""
        return HomeFeedItem(
            type="post",
            id=post["id"],
            title=post.get("title", ""),
            body=post.get("body", ""),
            author_name=post.get("author_name", "匿名"),
            author_avatar=post.get("author_avatar"),
            created_at=post.get("created_at", 0),
            tags=post.get("tags"),
        )

    def _transform_microblog(self, post: Dict) -> HomeFeedItem:
        """转换微博"""
        return HomeFeedItem(
            type="microblog",
            id=post["id"],
            title=None,
            body=post.get("content", post.get("body", "")),
            author_name=post.get("author_name", "匿名"),
            author_avatar=post.get("author_avatar"),
            created_at=post.get("created_at", 0),
        )

    def _transform_note(self, note: Dict) -> HomeFeedItem:
        """转换笔记"""
        return HomeFeedItem(
            type="note",
            id=note["id"],
            title=note.get("title", ""),
            body=note.get("body", ""),
            author_name=note.get("author_name", "匿名"),
            author_avatar=note.get("author_avatar"),
            created_at=note.get("created_at", 0),
        )

    # ========================================================
    #  数据获取
    # ========================================================

    async def get_feed(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取混合内容流"""
        items: List[HomeFeedItem] = []

        # 博客
        blog_plugin = self._get_plugin("blog")
        if blog_plugin:
            try:
                posts = await blog_plugin.list_posts(limit=limit)
                for p in posts:
                    items.append(self._transform_blog_post(p))
            except Exception as e:
                log.warning(f"Failed to get blog posts: {e}")

        # 微博
        microblog_plugin = self._get_plugin("microblog")
        if microblog_plugin:
            try:
                micro_posts = await microblog_plugin.list_posts(limit=limit)
                for p in micro_posts:
                    items.append(self._transform_microblog(p))
            except Exception as e:
                log.warning(f"Failed to get microblog posts: {e}")

        # 公开笔记
        notes_plugin = self._get_plugin("notes")
        if notes_plugin:
            try:
                notes = await notes_plugin.list_notes(visibility="public", limit=limit // 2)
                for n in notes:
                    items.append(self._transform_note(n))
            except Exception as e:
                log.warning(f"Failed to get notes: {e}")

        # 按时间倒序
        items.sort(key=lambda x: x.created_at, reverse=True)
        items = items[:limit]

        return [item.to_dict() for item in items]

    async def get_stats(self) -> HomeStats:
        """获取统计数字"""
        board_plugin = self._get_plugin("board")
        if board_plugin and hasattr(board_plugin, "get_stats"):
            try:
                stats = await board_plugin.get_stats()
                return HomeStats(
                    blog_count=int(stats.get("blog_count", 0)),
                    microblog_count=int(stats.get("microblog_count", 0)),
                    note_count=int(stats.get("note_count", 0)),
                )
            except Exception as e:
                log.warning(f"Failed to get stats: {e}")
        return HomeStats()

    async def get_active_authors(self, limit: int = 8) -> List[Dict[str, Any]]:
        """获取活跃作者"""
        board_plugin = self._get_plugin("board")
        if board_plugin and hasattr(board_plugin, "get_active_authors"):
            try:
                authors = await board_plugin.get_active_authors()
                return authors[:limit]
            except Exception as e:
                log.warning(f"Failed to get active authors: {e}")
        return []

    # ========================================================
    #  聚合接口
    # ========================================================

    async def get_home_data(self, feed_limit: int = 20) -> Dict[str, Any]:
        """一次性获取首页所需全部数据（并行查询）"""

        # 并行执行
        feed_task = asyncio.create_task(self.get_feed(feed_limit))
        stats_task = asyncio.create_task(self.get_stats())
        authors_task = asyncio.create_task(self.get_active_authors())

        results = await asyncio.gather(
            feed_task, stats_task, authors_task,
            return_exceptions=True
        )

        feed = results[0] if not isinstance(results[0], Exception) else []
        stats = results[1] if not isinstance(results[1], Exception) else HomeStats()
        authors = results[2] if not isinstance(results[2], Exception) else []

        if isinstance(results[0], Exception):
            log.error(f"Feed query failed: {results[0]}")
        if isinstance(results[1], Exception):
            log.error(f"Stats query failed: {results[1]}")
        if isinstance(results[2], Exception):
            log.error(f"Authors query failed: {results[2]}")

        return {
            "posts": feed,
            "blog_count": stats.blog_count,
            "microblog_count": stats.microblog_count,
            "note_count": stats.note_count,
            "active_authors": authors,
        }
