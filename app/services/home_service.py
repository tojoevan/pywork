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
    author_id: Optional[int]
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
            "author_id": self.author_id,
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
            author_id=post.get("author_id"),
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
            author_id=post.get("author_id"),
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
            author_id=note.get("author_id"),
            created_at=note.get("created_at", 0),
        )

    # ========================================================
    #  数据获取
    # ========================================================

    async def get_feed(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """获取混合内容流（全量合并后按页切片）

        各数据源一次性拉取后合并、按时间倒序，再做精确分页切片。
        这样总页数/末页/跳页都精确，避免各源独立按 offset 分页导致末页空白或重复。
        个人站点数据量小，全量合并开销可忽略；上限 10000 条作安全护栏。
        """
        items: List[HomeFeedItem] = []
        FETCH_CAP = 10000

        # 博客
        blog_plugin = self._get_plugin("blog")
        if blog_plugin:
            try:
                posts = await blog_plugin.list_posts(limit=FETCH_CAP)
                for p in posts:
                    items.append(self._transform_blog_post(p))
            except Exception as e:
                log.warning(f"Failed to get blog posts: {e}")

        # 微博
        microblog_plugin = self._get_plugin("microblog")
        if microblog_plugin:
            try:
                micro_posts = await microblog_plugin.list_posts(limit=FETCH_CAP)
                for p in micro_posts:
                    items.append(self._transform_microblog(p))
            except Exception as e:
                log.warning(f"Failed to get microblog posts: {e}")

        # 公开笔记
        notes_plugin = self._get_plugin("notes")
        if notes_plugin:
            try:
                notes = await notes_plugin.list_notes(visibility="public", limit=FETCH_CAP)
                for n in notes:
                    items.append(self._transform_note(n))
            except Exception as e:
                log.warning(f"Failed to get notes: {e}")

        # 按时间倒序
        items.sort(key=lambda x: x.created_at, reverse=True)
        total = len(items)

        # 越界（如跳到超过末页）则回退到最后一页
        if total > 0 and offset >= total:
            offset = max(0, ((total - 1) // limit) * limit)
        page = offset // limit + 1 if total > 0 else 1

        page_items = items[offset: offset + limit]

        return {
            "items": [item.to_dict() for item in page_items],
            "total": total,
            "page": page,
            "has_more": offset + limit < total,
        }

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

    async def get_hot_tags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门标签"""
        board_plugin = self._get_plugin("board")
        if board_plugin and hasattr(board_plugin, "get_hot_tags"):
            try:
                tags = await board_plugin.get_hot_tags(limit=limit)
                return tags
            except Exception as e:
                log.warning(f"Failed to get hot tags: {e}")
        return []

    async def get_recent_comments(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最新评论"""
        board_plugin = self._get_plugin("board")
        if board_plugin and hasattr(board_plugin, "get_recent_comments"):
            try:
                comments = await board_plugin.get_recent_comments(limit=limit)
                return comments
            except Exception as e:
                log.warning(f"Failed to get recent comments: {e}")
        return []

    async def get_author_data(self, user_id: int, page: int = 1, page_size: int = 20) -> Optional[Dict[str, Any]]:
        """获取作者主页数据：用户信息 + 公开内容（博客/微博/笔记按时间排序，分页）"""
        # 获取用户信息
        auth_plugin = self._get_plugin("auth")
        if not auth_plugin:
            return None
        user = await auth_plugin.get_user(user_id)
        if not user:
            return None

        items: List[HomeFeedItem] = []

        # 博客
        blog_plugin = self._get_plugin("blog")
        if blog_plugin:
            try:
                posts = await blog_plugin.list_posts(author_id=user_id, status="public", limit=200)
                for p in posts:
                    items.append(self._transform_blog_post(p))
            except Exception as e:
                log.warning(f"Failed to get author blogs: {e}")

        # 微博
        microblog_plugin = self._get_plugin("microblog")
        if microblog_plugin:
            try:
                micro_posts = await microblog_plugin.list_posts(author_id=user_id, limit=200)
                for p in micro_posts:
                    items.append(self._transform_microblog(p))
            except Exception as e:
                log.warning(f"Failed to get author microblogs: {e}")

        # 笔记（公开）
        notes_plugin = self._get_plugin("notes")
        if notes_plugin:
            try:
                notes = await notes_plugin.list_notes(visibility="public", author_id=user_id, limit=200)
                for n in notes:
                    items.append(self._transform_note(n))
            except Exception as e:
                log.warning(f"Failed to get author notes: {e}")

        # 按时间倒序
        items.sort(key=lambda x: x.created_at, reverse=True)

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]

        return {
            "author": {
                "id": user["id"],
                "username": user.get("username", ""),
                "display_name": user.get("nickname") or user.get("display_name") or user.get("username", ""),
                "avatar": user.get("avatar"),
                "created_at": user.get("created_at", 0),
            },
            "posts": [item.to_dict() for item in page_items],
            "blog_count": sum(1 for i in items if i.type == "post"),
            "microblog_count": sum(1 for i in items if i.type == "microblog"),
            "note_count": sum(1 for i in items if i.type == "note"),
            "page": page,
            "total_pages": total_pages,
            "total": total,
        }

    # ========================================================
    #  聚合接口
    # ========================================================

    async def get_home_data(self, feed_limit: int = 20, feed_offset: int = 0, page: int = 1) -> Dict[str, Any]:
        """一次性获取首页所需全部数据（并行查询）"""

        # 并行执行
        feed_task = asyncio.create_task(self.get_feed(feed_limit, feed_offset))
        stats_task = asyncio.create_task(self.get_stats())
        authors_task = asyncio.create_task(self.get_active_authors())
        tags_task = asyncio.create_task(self.get_hot_tags())
        comments_task = asyncio.create_task(self.get_recent_comments())

        results = await asyncio.gather(
            feed_task, stats_task, authors_task, tags_task, comments_task,
            return_exceptions=True
        )

        feed = results[0] if not isinstance(results[0], Exception) else {"items": [], "has_more": False, "total": 0, "page": 1}
        stats = results[1] if not isinstance(results[1], Exception) else HomeStats()
        authors = results[2] if not isinstance(results[2], Exception) else []
        hot_tags = results[3] if not isinstance(results[3], Exception) else []
        recent_comments = results[4] if not isinstance(results[4], Exception) else []

        if isinstance(results[0], Exception):
            log.error(f"Feed query failed: {results[0]}")
        if isinstance(results[1], Exception):
            log.error(f"Stats query failed: {results[1]}")
        if isinstance(results[2], Exception):
            log.error(f"Authors query failed: {results[2]}")
        if isinstance(results[3], Exception):
            log.error(f"Hot tags query failed: {results[3]}")
        if isinstance(results[4], Exception):
            log.error(f"Recent comments query failed: {results[4]}")

        total = feed.get("total", 0)
        page = feed.get("page", page)
        total_pages = max(1, (total + feed_limit - 1) // feed_limit) if total > 0 else 1

        # 页码窗口：始终显示首页与末页，中间以滑动窗口 + 省略号呈现
        page_window, show_start_ellipsis, show_end_ellipsis = self._build_page_window(page, total_pages, spread=3)

        return {
            "posts": feed["items"],
            "has_more": feed["has_more"],
            "page": page,
            "total_pages": total_pages,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if feed["has_more"] else None,
            "page_window": page_window,
            "show_start_ellipsis": show_start_ellipsis,
            "show_end_ellipsis": show_end_ellipsis,
            "blog_count": stats.blog_count,
            "microblog_count": stats.microblog_count,
            "note_count": stats.note_count,
            "active_authors": authors,
            "hot_tags": hot_tags,
            "recent_comments": recent_comments,
        }

    @staticmethod
    def _build_page_window(current: int, total_pages: int, spread: int = 3):
        """生成中间页码窗口与省略号标记（首页 1 与末页 total_pages 由模板单独渲染）"""
        if total_pages <= 1:
            return [], False, False
        left = max(2, current - spread)
        right = min(total_pages - 1, current + spread)
        if left > right:
            # 窗口塌缩（如总页数很少），不渲染中间段
            return [], False, False
        show_start_ellipsis = left > 2
        show_end_ellipsis = right < total_pages - 1
        return list(range(left, right + 1)), show_start_ellipsis, show_end_ellipsis
