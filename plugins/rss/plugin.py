"""RSS 阅读器插件 - 订阅 Feed、时间线展示、OPML 导入导出"""
import asyncio
import calendar
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.parse import urlparse

import aiohttp
import feedparser

from app.plugin import Plugin, PluginContext, Route


class RssPlugin(Plugin):

    @property
    def name(self) -> str:
        return "rss"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.template_engine = ctx.template_engine
        self.ctx = ctx
        self._ctx = ctx
        self._fetch_task = None
        self._fetch_running = False
        self._semaphore = asyncio.Semaphore(3)

    def routes(self) -> List[Route]:
        return [
            Route("/rss", "GET", self.rss_page),
            Route("/rss/feeds", "POST", self.add_feed_api),
            Route("/rss/feeds/{feed_id}", "DELETE", self.delete_feed_api),
            Route("/rss/feeds/{feed_id}/refresh", "POST", self.refresh_feed_api),
            Route("/rss/opml/import", "POST", self.import_opml_api),
            Route("/rss/opml/export", "GET", self.export_opml_api),
            Route("/rss/api/feeds", "GET", self.list_feeds_api),
            Route("/rss/api/items", "GET", self.list_items_api),
        ]

    # === 生命周期 ===

    async def on_start(self) -> None:
        self._fetch_running = True
        self._fetch_task = asyncio.create_task(self._fetch_loop())
        self.log.info("RSS fetcher started")

    async def on_stop(self) -> None:
        self._fetch_running = False
        if self._fetch_task:
            self._fetch_task.cancel()
            try:
                await self._fetch_task
            except asyncio.CancelledError:
                pass
        self.log.info("RSS fetcher stopped")

    # === 后台抓取 ===

    async def _fetch_loop(self) -> None:
        await asyncio.sleep(10)
        while self._fetch_running:
            try:
                now_ts = int(time.time())
                rows = await self.engine.fetchall(
                    "SELECT id, fetch_interval, last_fetched FROM rss_feeds ORDER BY id"
                )
                feed_ids = [
                    row["id"] for row in rows
                    if now_ts - row["last_fetched"] >= row["fetch_interval"]
                ]
                if not feed_ids:
                    await self._wait_until_next_hour()
                    continue

                cycle_start = int(time.time())
                for fid in feed_ids:
                    if not self._fetch_running:
                        return
                    try:
                        await self.fetch_feed(fid)
                    except Exception as e:
                        self.log.error(f"RSS fetch feed {fid} error: {e}")
                    if self._fetch_running:
                        await asyncio.sleep(60)

                elapsed = int(time.time()) - cycle_start
                self.log.info(f"RSS cycle done, {len(feed_ids)} feeds, {elapsed}s elapsed")
                await self._wait_until_next_hour()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.log.error(f"RSS fetch loop error: {e}")
                await self._wait_until_next_hour()

    async def _wait_until_next_hour(self) -> None:
        """等到下一个整点小时"""
        now = time.time()
        next_hour = (int(now) // 3600 + 1) * 3600
        wait = next_hour - now
        self.log.info(f"RSS fetcher sleeping {wait:.0f}s until next hour")
        await asyncio.sleep(wait)

    # === 核心数据方法 ===

    async def add_feed(self, url: str, added_by: int) -> dict:
        url = url.strip()
        if not url:
            return {"error": "URL 不能为空"}
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"error": "URL 必须以 http:// 或 https:// 开头"}

        now = int(time.time())
        try:
            await self.engine.execute(
                "INSERT INTO rss_feeds (url, added_by, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (url, added_by, now, now)
            )
        except Exception:
            return {"error": "该 Feed URL 已存在"}

        row = await self.engine.fetchone(
            "SELECT id FROM rss_feeds WHERE url = ?", (url,)
        )
        feed_id = row["id"] if row else None
        if feed_id:
            asyncio.create_task(self.fetch_feed(feed_id))
        return {"success": True, "feed_id": feed_id, "url": url}

    async def delete_feed(self, feed_id: int) -> dict:
        await self.engine.execute("DELETE FROM rss_items WHERE feed_id = ?", (feed_id,))
        await self.engine.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
        return {"success": True}

    async def list_feeds(self) -> list:
        rows = await self.engine.fetchall(
            "SELECT * FROM rss_feeds ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    async def list_items(self, page: int = 1, per_page: int = 30) -> dict:
        page = max(1, page)
        offset = (page - 1) * per_page
        total_row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM rss_items")
        total = total_row["cnt"] if total_row else 0
        rows = await self.engine.fetchall(
            "SELECT i.*, f.title as feed_title, f.site_url as feed_site_url "
            "FROM rss_items i LEFT JOIN rss_feeds f ON i.feed_id = f.id "
            "ORDER BY i.published_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            "items": [dict(r) for r in rows],
            "pagination": {"page": page, "total": total, "total_pages": total_pages}
        }

    async def fetch_feed(self, feed_id: int) -> dict:
        async with self._semaphore:
            feed = await self.engine.fetchone(
                "SELECT * FROM rss_feeds WHERE id = ?", (feed_id,)
            )
            if not feed:
                return {"error": "Feed 不存在"}

            url = feed["url"]
            now = int(time.time())

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={"User-Agent": "pyWork RSS Reader/1.0"},
                    ) as resp:
                        if resp.status != 200:
                            raise Exception(f"HTTP {resp.status}")
                        text = await resp.text()
            except Exception as e:
                await self.engine.execute(
                    "UPDATE rss_feeds SET last_error = ?, updated_at = ? WHERE id = ?",
                    (str(e)[:500], now, feed_id)
                )
                return {"error": str(e)}

            try:
                parsed = feedparser.parse(text)
            except Exception as e:
                await self.engine.execute(
                    "UPDATE rss_feeds SET last_error = ?, updated_at = ? WHERE id = ?",
                    (f"Parse error: {e}", now, feed_id)
                )
                return {"error": f"Parse error: {e}"}

            feed_info = parsed.get("feed", {})
            title = feed_info.get("title", feed["title"] or "")
            description = feed_info.get("description", feed["description"] or "")
            site_url = feed_info.get("link", feed["site_url"] or "")

            inserted = 0
            for entry in parsed.get("entries", []):
                guid = entry.get("id") or entry.get("link") or ""
                if not guid:
                    guid = hashlib.md5(
                        (entry.get("title", "") + str(entry.get("published_parsed", ""))).encode()
                    ).hexdigest()

                entry_title = entry.get("title", "")
                link = entry.get("link", "")
                desc = entry.get("summary") or entry.get("content", [{}])[0].get("value", "") if entry.get("content") else entry.get("summary", "")
                author = entry.get("author", "")
                published_at = self._parse_entry_date(entry)

                try:
                    await self.engine.execute(
                        "INSERT OR IGNORE INTO rss_items "
                        "(feed_id, guid, title, link, description, author, published_at, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (feed_id, guid, entry_title, link, desc, author, published_at, now, now)
                    )
                    inserted += 1
                except Exception:
                    pass

            await self.engine.execute(
                "UPDATE rss_feeds SET title = ?, description = ?, site_url = ?, "
                "last_fetched = ?, last_error = '', updated_at = ? WHERE id = ?",
                (title, description, site_url, now, now, feed_id)
            )
            return {"success": True, "feed_id": feed_id, "inserted": inserted}

    async def fetch_all_feeds(self) -> list:
        feeds = await self.list_feeds()
        results = []
        for feed in feeds:
            result = await self.fetch_feed(feed["id"])
            results.append(result)
        return results

    @staticmethod
    def _parse_entry_date(entry) -> int:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return int(calendar.timegm(entry.published_parsed))
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return int(calendar.timegm(entry.updated_parsed))
        return int(time.time())

    # === OPML ===

    async def parse_opml(self, opml_text: str) -> list:
        feeds = []
        try:
            root = ET.fromstring(opml_text)
        except ET.ParseError:
            return feeds
        for outline in root.iter("outline"):
            xml_url = outline.get("xmlUrl") or outline.get("xmlurl") or ""
            if not xml_url:
                continue
            feeds.append({
                "url": xml_url,
                "title": outline.get("title") or outline.get("text") or "",
                "site_url": outline.get("htmlUrl") or outline.get("htmlurl") or "",
            })
        return feeds

    async def import_opml(self, opml_text: str, added_by: int) -> dict:
        feeds = await self.parse_opml(opml_text)
        imported = 0
        skipped = 0
        for f in feeds:
            result = await self.add_feed(f["url"], added_by)
            if result.get("success"):
                imported += 1
            else:
                skipped += 1
        return {"imported": imported, "skipped": skipped, "total": len(feeds)}

    async def export_opml(self) -> str:
        feeds = await self.list_feeds()
        opml = ET.Element("opml", version="2.0")
        head = ET.SubElement(opml, "head")
        title_el = ET.SubElement(head, "title")
        title_el.text = "pyWork RSS Feeds"
        body = ET.SubElement(opml, "body")
        group = ET.SubElement(body, "outline", text="All Feeds", title="All Feeds")
        for feed in feeds:
            ET.SubElement(group, "outline",
                          type="rss",
                          text=feed.get("title") or feed.get("url", ""),
                          title=feed.get("title") or feed.get("url", ""),
                          xmlUrl=feed.get("url", ""),
                          htmlUrl=feed.get("site_url", ""))
        ET.indent(opml)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(opml, encoding="unicode")

    # === HTTP 处理器 ===

    async def rss_page(self, request, **kwargs):
        page = int(kwargs.get("page", 1))
        user = await self.get_current_user(request)
        data = await self.list_items(page=page, per_page=30)
        feeds = await self.list_feeds()
        html = await self.template_engine.render("rss.html", {
            "nav_page": "rss",
            "User": user,
            "items": data["items"],
            "pagination": data["pagination"],
            "feeds": feeds,
        })
        from starlette.responses import HTMLResponse
        return HTMLResponse(html)

    async def add_feed_api(self, request, **kwargs):
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("未登录", 401)
        url = kwargs.get("url", "").strip()
        if not url:
            return self.error_json("URL 不能为空", 400)
        result = await self.add_feed(url, user["id"])
        if result.get("error"):
            return self.error_json(result["error"], 400)
        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def delete_feed_api(self, request, **kwargs):
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("未登录", 401)
        feed_id = int(kwargs.get("feed_id", 0))
        feed = await self.engine.fetchone("SELECT * FROM rss_feeds WHERE id = ?", (feed_id,))
        if not feed:
            return self.error_json("Feed 不存在", 404)
        if feed["added_by"] != user["id"] and user.get("role") != "admin":
            return self.error_json("无权限删除", 403)
        result = await self.delete_feed(feed_id)
        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def refresh_feed_api(self, request, **kwargs):
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("未登录", 401)
        feed_id = int(kwargs.get("feed_id", 0))
        result = await self.fetch_feed(feed_id)
        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def import_opml_api(self, request, **kwargs):
        user = await self.get_current_user(request)
        if not user:
            return self.error_json("未登录", 401)
        try:
            form = await request.form()
            file = form.get("opml_file") or form.get("file")
            if not file:
                return self.error_json("请选择 OPML 文件", 400)
            content = await file.read()
            opml_text = content.decode("utf-8")
        except Exception as e:
            return self.error_json(f"读取文件失败: {e}", 400)
        result = await self.import_opml(opml_text, user["id"])
        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def export_opml_api(self, request, **kwargs):
        opml_text = await self.export_opml()
        from starlette.responses import Response
        return Response(
            content=opml_text,
            media_type="application/xml; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="rss_feeds.opml"'}
        )

    async def list_feeds_api(self, request, **kwargs):
        feeds = await self.list_feeds()
        from starlette.responses import JSONResponse
        return JSONResponse({"feeds": feeds})

    async def list_items_api(self, request, **kwargs):
        page = int(kwargs.get("page", 1))
        data = await self.list_items(page=page, per_page=30)
        from starlette.responses import JSONResponse
        return JSONResponse(data)
