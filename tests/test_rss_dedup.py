"""RSS 时间线去重 / 多来源聚合 —— 真 SQLite 集成测试.

tests/test_rss.py 里的 MockEngine 是按 SQL 字符串特征模拟查询，验证不了真实 SQL 的
CTE / GROUP BY / IN 行为，改 SQL 时会「假通过」。这里用内存 SQLite 跑 list_items
的真实 SQL，覆盖去重、来源聚合、分页与回退逻辑。
"""
import sqlite3

import pytest

from plugins.rss.plugin import RssPlugin


class AsyncSQLiteEngine:
    """最小 engine 适配器：只实现 list_items 用到的 fetchone / fetchall。"""

    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE rss_feeds ("
            "  id INTEGER PRIMARY KEY, title TEXT DEFAULT '', "
            "  site_url TEXT DEFAULT '', url TEXT DEFAULT '')"
        )
        self.con.execute(
            "CREATE TABLE rss_items ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT, feed_id INTEGER NOT NULL, "
            "  guid TEXT NOT NULL, title TEXT DEFAULT '', link TEXT DEFAULT '', "
            "  description TEXT DEFAULT '', author TEXT DEFAULT '', "
            "  published_at INTEGER NOT NULL, created_at INTEGER DEFAULT 0, "
            "  updated_at INTEGER DEFAULT 0, UNIQUE(feed_id, guid))"
        )

    async def fetchone(self, sql, params=()):
        row = self.con.execute(sql, params).fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql, params=()):
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    def add_feed(self, feed_id, title, site_url):
        self.con.execute(
            "INSERT INTO rss_feeds (id, title, site_url, url) VALUES (?, ?, ?, ?)",
            (feed_id, title, site_url, "https://example.com/feed.xml"),
        )

    def add_item(self, feed_id, guid, title, link, published_at=1000):
        self.con.execute(
            "INSERT INTO rss_items "
            "(feed_id, guid, title, link, description, author, published_at) "
            "VALUES (?, ?, ?, ?, '', '', ?)",
            (feed_id, guid, title, link, published_at),
        )

    def close(self):
        self.con.close()


@pytest.fixture
def engine():
    e = AsyncSQLiteEngine()
    yield e
    e.close()


def make_plugin(engine):
    plugin = RssPlugin()
    plugin.engine = engine
    return plugin


@pytest.mark.asyncio
async def test_same_link_across_feeds_is_merged_with_all_sources(engine):
    engine.add_feed(1, "AIHOT — 精选", "https://aihot.news/")
    engine.add_feed(2, "AIHOT — 全部 AI 动态", "https://aihot.news/all")
    link = "https://aihot.news/items/abc"
    engine.add_item(1, "abc", "同一篇新闻", link, 1000)
    engine.add_item(2, "abc", "同一篇新闻", link, 1000)

    data = await make_plugin(engine).list_items(page=1, per_page=30)

    assert data["pagination"]["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["title"] == "同一篇新闻"
    assert item["source_count"] == 2
    assert [s["title"] for s in item["sources"]] == [
        "AIHOT — 精选", "AIHOT — 全部 AI 动态",
    ]
    assert [s["site_url"] for s in item["sources"]] == [
        "https://aihot.news/", "https://aihot.news/all",
    ]


@pytest.mark.asyncio
async def test_total_and_pagination_use_deduped_count(engine):
    engine.add_feed(1, "精选", "https://a.example")
    engine.add_feed(2, "全部", "https://b.example")
    # 5 篇文章，其中 2 篇被两个源各收录一次 -> 7 行、5 篇
    for i in range(5):
        link = "https://example.com/%d" % i
        engine.add_item(1, "g%d" % i, "文章 %d" % i, link, 1000 + i)
        if i in (1, 3):
            engine.add_item(2, "g%d" % i, "文章 %d" % i, link, 1000 + i)

    plugin = make_plugin(engine)
    first = await plugin.list_items(page=1, per_page=2)
    assert first["pagination"]["total"] == 5
    assert first["pagination"]["total_pages"] == 3

    seen = []
    for page in (1, 2, 3):
        data = await plugin.list_items(page=page, per_page=2)
        seen.extend(item["link"] for item in data["items"])
    assert len(seen) == 5
    assert len(set(seen)) == 5  # 无重复
    assert set(seen) == {"https://example.com/%d" % i for i in range(5)}  # 无遗漏


@pytest.mark.asyncio
async def test_empty_link_falls_back_to_guid(engine):
    engine.add_feed(1, "精选", "https://a.example")
    engine.add_feed(2, "全部", "https://b.example")
    engine.add_item(1, "same-guid", "无链接文章", "", 1000)
    engine.add_item(2, "same-guid", "无链接文章", "", 1000)

    data = await make_plugin(engine).list_items(page=1, per_page=30)
    assert data["pagination"]["total"] == 1
    assert data["items"][0]["source_count"] == 2


@pytest.mark.asyncio
async def test_different_links_are_not_merged(engine):
    engine.add_feed(1, "精选", "https://a.example")
    engine.add_item(1, "g1", "文章 A", "https://example.com/a", 1000)
    engine.add_item(1, "g2", "文章 B", "https://example.com/b", 2000)

    data = await make_plugin(engine).list_items(page=1, per_page=30)
    assert data["pagination"]["total"] == 2
    assert [i["title"] for i in data["items"]] == ["文章 B", "文章 A"]
    assert all(i["source_count"] == 1 for i in data["items"])


@pytest.mark.asyncio
async def test_three_or_more_sources_all_listed(engine):
    for fid in (1, 2, 3, 4):
        engine.add_feed(fid, "源%d" % fid, "https://%d.example" % fid)
    link = "https://example.com/shared"
    for fid in (1, 2, 3, 4):
        engine.add_item(fid, "shared", "多方转载", link, 1000)

    data = await make_plugin(engine).list_items(page=1, per_page=30)
    assert data["pagination"]["total"] == 1
    item = data["items"][0]
    assert item["source_count"] == 4
    assert len(item["sources"]) == 4
    assert len({s["feed_id"] for s in item["sources"]}) == 4
