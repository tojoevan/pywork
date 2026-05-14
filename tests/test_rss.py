"""Tests for plugins/rss/plugin.py — RssPlugin"""
import asyncio
import pytest
import time
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional


class MockEngine:
    def __init__(self):
        self.tables: Dict[str, Dict[int, Dict]] = {}
        self._next_id: Dict[str, int] = {}
        self._executed: List[tuple] = []

    def _ensure_table(self, table):
        if table not in self.tables:
            self.tables[table] = {}
            self._next_id[table] = 1

    async def get(self, table, id):
        self._ensure_table(table)
        row = self.tables[table].get(id)
        return dict(row) if row else None

    async def put(self, table, id, data):
        self._ensure_table(table)
        if id == 0:
            id = self._next_id[table]
            self._next_id[table] += 1
        data = data.copy()
        data["id"] = id
        self.tables[table][id] = data
        return id

    async def delete(self, table, id):
        self._ensure_table(table)
        self.tables[table].pop(id, None)

    async def fetchone(self, sql, params=()):
        self._executed.append((sql, params))
        if "rss_feeds" in sql and "WHERE url" in sql:
            url = params[0] if params else None
            for row in self.tables.get("rss_feeds", {}).values():
                if row.get("url") == url:
                    return dict(row)
            return None
        if "rss_feeds" in sql and "WHERE id" in sql:
            fid = params[0] if params else None
            row = self.tables.get("rss_feeds", {}).get(fid)
            return dict(row) if row else None
        if "COUNT(*)" in sql and "rss_items" in sql:
            return {"cnt": len(self.tables.get("rss_items", {}))}
        return None

    async def fetchall(self, sql, params=()):
        self._executed.append((sql, params))
        if "rss_items" in sql and "rss_feeds" in sql:
            items = sorted(self.tables.get("rss_items", {}).values(),
                           key=lambda x: x.get("published_at", 0), reverse=True)
            results = []
            for item in items:
                row = dict(item)
                feed = self.tables.get("rss_feeds", {}).get(item.get("feed_id"))
                row["feed_title"] = feed.get("title", "") if feed else ""
                row["feed_site_url"] = feed.get("site_url", "") if feed else ""
                results.append(row)
            limit = params[0] if len(params) > 0 else 30
            offset = params[1] if len(params) > 1 else 0
            return results[offset:offset + limit]
        if "rss_items" in sql:
            results = []
            for item in self.tables.get("rss_items", {}).values():
                if f"feed_id = {params[0]}" in sql or len(params) == 0:
                    results.append(dict(item))
            return results
        if "rss_feeds" in sql and "ORDER BY created_at" in sql:
            results = sorted(self.tables.get("rss_feeds", {}).values(),
                             key=lambda x: x.get("created_at", 0), reverse=True)
            return [dict(r) for r in results]
        if "rss_feeds" in sql and ("last_fetched = 0" in sql or "fetch_interval" in sql):
            now = int(time.time())
            results = []
            for row in self.tables.get("rss_feeds", {}).values():
                if row.get("last_fetched", 0) == 0 or \
                   row.get("last_fetched", 0) + row.get("fetch_interval", 1800) <= now:
                    results.append(dict(row))
            return results
        if "rss_feeds" in sql:
            return [dict(r) for r in self.tables.get("rss_feeds", {}).values()]
        return []

    async def execute(self, sql, params=()):
        self._executed.append((sql, params))
        if "INSERT INTO rss_feeds" in sql:
            self._ensure_table("rss_feeds")
            url = params[0]
            for row in self.tables["rss_feeds"].values():
                if row.get("url") == url:
                    raise Exception("UNIQUE constraint failed")
            fid = self._next_id["rss_feeds"]
            self._next_id["rss_feeds"] += 1
            self.tables["rss_feeds"][fid] = {
                "id": fid, "url": params[0], "title": "", "description": "",
                "site_url": "", "last_fetched": 0, "last_error": "",
                "fetch_interval": 1800, "added_by": params[1],
                "created_at": params[2], "updated_at": params[3],
            }
        if "INSERT OR IGNORE INTO rss_items" in sql:
            self._ensure_table("rss_items")
            feed_id, guid = params[0], params[1]
            for row in self.tables["rss_items"].values():
                if row.get("feed_id") == feed_id and row.get("guid") == guid:
                    return  # IGNORE
            iid = self._next_id["rss_items"]
            self._next_id["rss_items"] += 1
            self.tables["rss_items"][iid] = {
                "id": iid, "feed_id": params[0], "guid": params[1],
                "title": params[2], "link": params[3], "description": params[4],
                "author": params[5], "published_at": params[6],
                "created_at": params[7], "updated_at": params[8],
            }
        if "DELETE FROM rss_items WHERE feed_id" in sql:
            fid = params[0]
            to_del = [k for k, v in self.tables.get("rss_items", {}).items() if v.get("feed_id") == fid]
            for k in to_del:
                self.tables["rss_items"].pop(k, None)
        if "DELETE FROM rss_feeds WHERE id" in sql:
            self.tables.get("rss_feeds", {}).pop(params[0], None)
        if "UPDATE rss_feeds SET title" in sql:
            fid = params[-1]
            row = self.tables.get("rss_feeds", {}).get(fid)
            if row:
                row["title"] = params[0]
                row["description"] = params[1]
                row["site_url"] = params[2]
                row["last_fetched"] = params[3]
                row["last_error"] = ""
                row["updated_at"] = params[4]
        if "UPDATE rss_feeds SET last_error" in sql:
            fid = params[-1]
            row = self.tables.get("rss_feeds", {}).get(fid)
            if row:
                row["last_error"] = params[0]
                row["updated_at"] = params[1]


def seed_feed(engine, feed_id, url="https://example.com/feed.xml", title="Test Feed",
              added_by=1, last_fetched=0):
    now = int(time.time())
    engine._ensure_table("rss_feeds")
    engine.tables["rss_feeds"][feed_id] = {
        "id": feed_id, "url": url, "title": title, "description": "desc",
        "site_url": "https://example.com", "last_fetched": last_fetched,
        "last_error": "", "fetch_interval": 1800, "added_by": added_by,
        "created_at": now, "updated_at": now,
    }
    if feed_id >= engine._next_id.get("rss_feeds", 1):
        engine._next_id["rss_feeds"] = feed_id + 1
    return engine.tables["rss_feeds"][feed_id]


def seed_item(engine, item_id, feed_id, guid="item-1", title="Article",
              published_at=None):
    now = int(time.time())
    engine._ensure_table("rss_items")
    engine.tables["rss_items"][item_id] = {
        "id": item_id, "feed_id": feed_id, "guid": guid,
        "title": title, "link": "https://example.com/article",
        "description": "<p>Content</p>", "author": "Author",
        "published_at": published_at or now, "created_at": now, "updated_at": now,
    }
    if item_id >= engine._next_id.get("rss_items", 1):
        engine._next_id["rss_items"] = item_id + 1


async def init_plugin(engine=None, user=None):
    from plugins.rss.plugin import RssPlugin
    plugin = RssPlugin()
    engine = engine or MockEngine()
    plugin.engine = engine
    plugin.template_engine = MagicMock()
    plugin.template_engine.render = AsyncMock(return_value="<html></html>")
    plugin.config = {}
    plugin.ctx = MagicMock()
    plugin.ctx.engine = engine
    plugin._ctx = plugin.ctx
    plugin._fetch_task = None
    plugin._fetch_running = False
    plugin._semaphore = AsyncMock()
    plugin._semaphore.__aenter__ = AsyncMock()
    plugin._semaphore.__aexit__ = AsyncMock()

    auth = MagicMock()
    auth.get_user_by_token = AsyncMock(return_value=user)
    auth.get_user_by_mcp_token = AsyncMock(return_value=user)
    plugin.ctx.get_plugin = MagicMock(return_value=auth)

    from app.log import get_logger
    plugin._logger = get_logger("test.rss", "test.rss")

    return plugin, engine


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <description>A test blog</description>
    <item>
      <title>First Post</title>
      <link>https://example.com/first</link>
      <description>First post content</description>
      <author>Author1</author>
      <pubDate>Wed, 14 May 2026 10:00:00 +0000</pubDate>
      <guid>https://example.com/first</guid>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/second</link>
      <description>Second post content</description>
      <author>Author2</author>
      <pubDate>Wed, 14 May 2026 08:00:00 +0000</pubDate>
      <guid>https://example.com/second</guid>
    </item>
  </channel>
</rss>"""

SAMPLE_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Subscriptions</title></head>
  <body>
    <outline text="Tech" title="Tech">
      <outline type="rss" text="Hacker News" title="Hacker News"
               xmlUrl="https://hnrss.org/frontpage"
               htmlUrl="https://news.ycombinator.com"/>
      <outline type="rss" text="TechCrunch" title="TechCrunch"
               xmlUrl="https://techcrunch.com/feed/"
               htmlUrl="https://techcrunch.com"/>
    </outline>
  </body>
</opml>"""


# ============================================================
#  Plugin Properties
# ============================================================

class TestRssPluginProperties:
    @pytest.mark.asyncio
    async def test_name(self):
        plugin, _ = await init_plugin()
        assert plugin.name == "rss"

    @pytest.mark.asyncio
    async def test_routes_count(self):
        plugin, _ = await init_plugin()
        routes = plugin.routes()
        assert len(routes) == 8

    @pytest.mark.asyncio
    async def test_routes_paths(self):
        plugin, _ = await init_plugin()
        paths = [r.path for r in plugin.routes()]
        assert "/rss" in paths
        assert "/rss/feeds" in paths
        assert "/rss/opml/export" in paths
        assert "/rss/opml/import" in paths


# ============================================================
#  Add Feed
# ============================================================

class TestAddFeed:
    @pytest.mark.asyncio
    async def test_add_feed_success(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.add_feed("https://example.com/feed.xml", added_by=1)
        assert result.get("success") is True
        assert result.get("feed_id") is not None
        assert len(engine.tables.get("rss_feeds", {})) == 1

    @pytest.mark.asyncio
    async def test_add_feed_empty_url(self):
        plugin, _ = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.add_feed("", added_by=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_feed_invalid_scheme(self):
        plugin, _ = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.add_feed("ftp://example.com/feed", added_by=1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_add_feed_duplicate(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1, url="https://example.com/feed.xml")
        result = await plugin.add_feed("https://example.com/feed.xml", added_by=1)
        assert "error" in result


# ============================================================
#  Delete Feed
# ============================================================

class TestDeleteFeed:
    @pytest.mark.asyncio
    async def test_delete_feed_success(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1)
        result = await plugin.delete_feed(1)
        assert result.get("success") is True
        assert len(engine.tables.get("rss_feeds", {})) == 0
        assert len(engine.tables.get("rss_items", {})) == 0

    @pytest.mark.asyncio
    async def test_delete_feed_cascades_items(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1, guid="a")
        seed_item(engine, 2, feed_id=1, guid="b")
        seed_item(engine, 3, feed_id=1, guid="c")
        await plugin.delete_feed(1)
        assert len(engine.tables.get("rss_items", {})) == 0


# ============================================================
#  List Feeds
# ============================================================

class TestListFeeds:
    @pytest.mark.asyncio
    async def test_list_feeds_empty(self):
        plugin, _ = await init_plugin()
        feeds = await plugin.list_feeds()
        assert feeds == []

    @pytest.mark.asyncio
    async def test_list_feeds_returns_all(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1, url="https://a.com/feed")
        seed_feed(engine, 2, url="https://b.com/feed")
        feeds = await plugin.list_feeds()
        assert len(feeds) == 2


# ============================================================
#  List Items
# ============================================================

class TestListItems:
    @pytest.mark.asyncio
    async def test_list_items_empty(self):
        plugin, _ = await init_plugin()
        data = await plugin.list_items(page=1, per_page=30)
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_items_with_data(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1, guid="a", published_at=1000)
        seed_item(engine, 2, feed_id=1, guid="b", published_at=2000)
        data = await plugin.list_items(page=1, per_page=30)
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_list_items_pagination(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        for i in range(5):
            seed_item(engine, i + 1, feed_id=1, guid=f"item-{i}", published_at=i * 100)
        data = await plugin.list_items(page=1, per_page=2)
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_list_items_includes_feed_title(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1, title="My Feed")
        seed_item(engine, 1, feed_id=1, guid="a")
        data = await plugin.list_items(page=1)
        assert data["items"][0]["feed_title"] == "My Feed"


# ============================================================
#  Fetch Feed
# ============================================================

class TestFetchFeed:
    @pytest.mark.asyncio
    async def test_fetch_feed_not_found(self):
        plugin, _ = await init_plugin()
        plugin._semaphore = MagicMock()
        plugin._semaphore.__aenter__ = AsyncMock()
        plugin._semaphore.__aexit__ = AsyncMock()
        result = await plugin.fetch_feed(999)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fetch_feed_success(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1, url="https://example.com/feed.xml")
        plugin._semaphore = MagicMock()
        plugin._semaphore.__aenter__ = AsyncMock()
        plugin._semaphore.__aexit__ = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=SAMPLE_RSS)

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("plugins.rss.plugin.aiohttp.ClientSession", return_value=mock_session):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            result = await plugin.fetch_feed(1)

        assert result.get("success") is True
        assert result.get("inserted") == 2
        feed = engine.tables["rss_feeds"][1]
        assert feed["title"] == "Test Blog"

    @pytest.mark.asyncio
    async def test_fetch_feed_http_error(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        plugin._semaphore = MagicMock()
        plugin._semaphore.__aenter__ = AsyncMock()
        plugin._semaphore.__aexit__ = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("plugins.rss.plugin.aiohttp.ClientSession", return_value=mock_session):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            result = await plugin.fetch_feed(1)

        assert "error" in result
        assert engine.tables["rss_feeds"][1]["last_error"] != ""

    @pytest.mark.asyncio
    async def test_fetch_feed_duplicate_items_ignored(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        plugin._semaphore = MagicMock()
        plugin._semaphore.__aenter__ = AsyncMock()
        plugin._semaphore.__aexit__ = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=SAMPLE_RSS)

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("plugins.rss.plugin.aiohttp.ClientSession", return_value=mock_session):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            await plugin.fetch_feed(1)
            await plugin.fetch_feed(1)

        items = [v for v in engine.tables.get("rss_items", {}).values() if v["feed_id"] == 1]
        assert len(items) == 2


# ============================================================
#  OPML Parse
# ============================================================

class TestOpmlParse:
    @pytest.mark.asyncio
    async def test_parse_opml_valid(self):
        plugin, _ = await init_plugin()
        feeds = await plugin.parse_opml(SAMPLE_OPML)
        assert len(feeds) == 2
        assert feeds[0]["url"] == "https://hnrss.org/frontpage"
        assert feeds[1]["url"] == "https://techcrunch.com/feed/"

    @pytest.mark.asyncio
    async def test_parse_opml_invalid_xml(self):
        plugin, _ = await init_plugin()
        feeds = await plugin.parse_opml("not xml at all")
        assert feeds == []

    @pytest.mark.asyncio
    async def test_parse_opml_no_feeds(self):
        plugin, _ = await init_plugin()
        feeds = await plugin.parse_opml("<opml><body></body></opml>")
        assert feeds == []

    @pytest.mark.asyncio
    async def test_parse_opml_extracts_attributes(self):
        plugin, _ = await init_plugin()
        feeds = await plugin.parse_opml(SAMPLE_OPML)
        assert feeds[0]["title"] == "Hacker News"
        assert feeds[0]["site_url"] == "https://news.ycombinator.com"


# ============================================================
#  OPML Import / Export
# ============================================================

class TestOpmlImportExport:
    @pytest.mark.asyncio
    async def test_import_opml(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.import_opml(SAMPLE_OPML, added_by=1)
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert len(engine.tables["rss_feeds"]) == 2

    @pytest.mark.asyncio
    async def test_import_opml_skips_duplicates(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1, url="https://hnrss.org/frontpage")
        result = await plugin.import_opml(SAMPLE_OPML, added_by=1)
        assert result["imported"] == 1
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_export_opml(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1, url="https://a.com/feed", title="Feed A")
        seed_feed(engine, 2, url="https://b.com/feed", title="Feed B")
        opml_text = await plugin.export_opml()
        assert '<?xml version="1.0"' in opml_text
        assert "https://a.com/feed" in opml_text
        assert "https://b.com/feed" in opml_text
        root = ET.fromstring(opml_text)
        outlines = root.findall(".//outline[@xmlUrl]")
        assert len(outlines) == 2

    @pytest.mark.asyncio
    async def test_export_opml_empty(self):
        plugin, _ = await init_plugin()
        opml_text = await plugin.export_opml()
        assert "pyWork RSS Feeds" in opml_text
        root = ET.fromstring(opml_text)
        outlines = root.findall(".//outline[@xmlUrl]")
        assert len(outlines) == 0

    @pytest.mark.asyncio
    async def test_export_roundtrip(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        await plugin.import_opml(SAMPLE_OPML, added_by=1)
        exported = await plugin.export_opml()
        root = ET.fromstring(exported)
        outlines = root.findall(".//outline[@xmlUrl]")
        assert len(outlines) == 2


# ============================================================
#  Date Parsing
# ============================================================

class TestDateParsing:
    def test_parse_entry_date_with_published(self):
        from plugins.rss.plugin import RssPlugin
        entry = MagicMock()
        entry.published_parsed = (2026, 5, 14, 10, 0, 0, 0, 0, 0)
        ts = RssPlugin._parse_entry_date(entry)
        assert isinstance(ts, int)
        assert ts > 0

    def test_parse_entry_date_fallback_to_updated(self):
        from plugins.rss.plugin import RssPlugin
        entry = MagicMock(spec=[])
        entry.updated_parsed = (2026, 5, 14, 10, 0, 0, 0, 0, 0)
        ts = RssPlugin._parse_entry_date(entry)
        assert isinstance(ts, int)

    def test_parse_entry_date_fallback_to_now(self):
        from plugins.rss.plugin import RssPlugin
        entry = MagicMock(spec=[])
        ts = RssPlugin._parse_entry_date(entry)
        assert isinstance(ts, int)
        assert abs(ts - int(time.time())) < 5


# ============================================================
#  HTTP Handlers
# ============================================================

class TestHttpHandlers:
    @pytest.mark.asyncio
    async def test_rss_page_renders(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1)
        mock_request = MagicMock()
        result = await plugin.rss_page(mock_request)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_add_feed_api_no_login(self):
        plugin, _ = await init_plugin(user=None)
        mock_request = MagicMock()
        result = await plugin.add_feed_api(mock_request, url="https://x.com/feed")
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_add_feed_api_success(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        mock_request = MagicMock()
        result = await plugin.add_feed_api(mock_request, url="https://x.com/feed")
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_add_feed_api_empty_url(self):
        plugin, _ = await init_plugin(user={"id": 1, "role": "user"})
        mock_request = MagicMock()
        result = await plugin.add_feed_api(mock_request, url="")
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_feed_api_no_permission(self):
        plugin, engine = await init_plugin(user={"id": 2, "role": "user"})
        seed_feed(engine, 1, added_by=1)
        mock_request = MagicMock()
        result = await plugin.delete_feed_api(mock_request, feed_id=1)
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_feed_api_owner(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        seed_feed(engine, 1, added_by=1)
        mock_request = MagicMock()
        result = await plugin.delete_feed_api(mock_request, feed_id=1)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_feed_api_admin(self):
        plugin, engine = await init_plugin(user={"id": 99, "role": "admin"})
        seed_feed(engine, 1, added_by=1)
        mock_request = MagicMock()
        result = await plugin.delete_feed_api(mock_request, feed_id=1)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_export_opml_api(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1, url="https://a.com/feed", title="A")
        mock_request = MagicMock()
        result = await plugin.export_opml_api(mock_request)
        assert result.status_code == 200
        assert "xml" in result.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_list_feeds_api(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        mock_request = MagicMock()
        result = await plugin.list_feeds_api(mock_request)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_list_items_api(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1)
        mock_request = MagicMock()
        result = await plugin.list_items_api(mock_request, page=1)
        assert result.status_code == 200


# ============================================================
#  Edge Cases
# ============================================================

class TestFetchSchedule:
    @pytest.mark.asyncio
    async def test_wait_until_next_hour(self):
        plugin, _ = await init_plugin()
        import time as _time
        start = _time.time()
        # Mock sleep to avoid actually waiting
        sleep_args = []
        original_sleep = asyncio.sleep

        async def mock_sleep(secs):
            sleep_args.append(secs)

        asyncio.sleep = mock_sleep
        try:
            await plugin._wait_until_next_hour()
        finally:
            asyncio.sleep = original_sleep
        assert len(sleep_args) == 1
        assert 0 < sleep_args[0] <= 3600

    @pytest.mark.asyncio
    async def test_fetch_loop_empty_feeds_waits(self):
        plugin, engine = await init_plugin()
        plugin._fetch_running = True
        calls = []

        async def mock_wait():
            calls.append("wait")
            plugin._fetch_running = False

        plugin._wait_until_next_hour = mock_wait
        await plugin._fetch_loop()
        assert "wait" in calls


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_fetch_all_feeds_empty(self):
        plugin, _ = await init_plugin()
        results = await plugin.fetch_all_feeds()
        assert results == []

    @pytest.mark.asyncio
    async def test_add_feed_strips_whitespace(self):
        plugin, engine = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.add_feed("  https://example.com/feed  ", added_by=1)
        assert result.get("success") is True
        feed = list(engine.tables["rss_feeds"].values())[0]
        assert feed["url"] == "https://example.com/feed"

    @pytest.mark.asyncio
    async def test_list_items_page_beyond_total(self):
        plugin, engine = await init_plugin()
        seed_feed(engine, 1)
        seed_item(engine, 1, feed_id=1)
        data = await plugin.list_items(page=99, per_page=30)
        assert data["items"] == []
        assert data["pagination"]["page"] == 99

    @pytest.mark.asyncio
    async def test_delete_nonexistent_feed(self):
        plugin, _ = await init_plugin(user={"id": 1, "role": "user"})
        result = await plugin.delete_feed(999)
        assert result.get("success") is True
