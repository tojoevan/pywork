"""看板页面插件 - 定时任务管理 + 看板（仅管理员可访问）"""
import time
import asyncio
import sqlite3
from typing import List, Dict, Any, Optional

from app.plugin import Plugin, PluginContext, Route


# ============================================================
#  定时任务配置
# ============================================================

# 预置任务定义：name → handler_key
PRESET_JOBS = {
    "stats_collection": {
        "name": "统计内容数量",
        "description": "每小时统计博客、微博、笔记数量并写入数据库",
        "interval": 3600,
        "cron_expr": "0 * * * *",
        "handler_key": "run_stats_collection",
    },
    "active_authors": {
        "name": "活跃作者统计",
        "description": "每小时统计活跃作者及写作数量并写入数据库",
        "interval": 3600,
        "cron_expr": "0 * * * *",
        "handler_key": "run_active_authors",
    },
}

# 间隔选项
INTERVAL_OPTIONS = [
    ("hourly",    "每小时"),
    ("daily",     "每天"),
    ("weekly",    "每周"),
]

# ============================================================
#  插件主类
# ============================================================

class BoardPlugin(Plugin):

    @property
    def name(self) -> str:
        return "board"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.template_engine = ctx.template_engine
        self.ctx = ctx
        # 任务处理器注册表
        self._handlers: Dict[str, callable] = {
            "run_stats_collection": self._handle_stats_collection,
            "run_active_authors":    self._handle_active_authors,
        }

    def routes(self) -> List[Route]:
        return [
            # 看板
            Route("/board", "GET", self.board_page, "board.page"),
            Route("/board/tasks", "POST", self.create_task, "board.create"),
            Route("/board/tasks/{task_id}", "PUT", self.update_task, "board.update"),
            Route("/board/tasks/{task_id}", "DELETE", self.delete_task, "board.delete"),
            # 定时任务
            Route("/board/cron", "GET", self.cron_page, "board.cron_page"),
            Route("/board/cron/jobs", "GET", self.list_cron_jobs_api, "board.cron_list"),
            Route("/board/cron/jobs", "POST", self.create_cron_job, "board.cron_create"),
            Route("/board/cron/jobs/{job_id}", "PUT", self.update_cron_job, "board.cron_update"),
            Route("/board/cron/jobs/{job_id}", "DELETE", self.delete_cron_job, "board.cron_delete"),
            Route("/board/cron/jobs/{job_id}/run", "POST", self.run_cron_job_api, "board.cron_run"),
            # 网站设置
            Route("/board/settings", "GET", self.settings_page, "board.settings_page"),
            Route("/board/settings/api", "GET", self.get_settings_api, "board.settings_get"),
            Route("/board/settings/api", "PUT", self.update_settings_api, "board.settings_update"),
            Route("/board/moderation", "GET", self.moderation_page, "board.moderation_page"),
        ]

    # ========================================================
    #  认证辅助
    # ========================================================

    def _auth(self):
        return self.ctx.get_plugin("auth")

    async def _get_current_user(self, request) -> Optional[Dict]:
        token = request.cookies.get("auth_token", "")
        if not token:
            return None
        auth = self._auth()
        if not auth:
            return None
        return await auth.get_user_by_token(token)

    async def _is_admin(self, request) -> bool:
        user = await self._get_current_user(request)
        return user is not None and user.get("role") == "admin"

    async def _check_admin(self, request):
        """非管理员返回 403 JSON"""
        if not await self._is_admin(request):
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return None

    async def _check_admin_or_redirect(self, request):
        from starlette.responses import RedirectResponse
        if not await self._is_admin(request):
            return RedirectResponse(url="/", status_code=302)
        return None

    # ========================================================
    #  看板表初始化
    # ========================================================

    async def _init_board_table(self):
        sql = """
        CREATE TABLE IF NOT EXISTS board_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee_id INTEGER DEFAULT NULL,
            assignee_name TEXT DEFAULT '',
            status TEXT DEFAULT 'todo',
            priority TEXT DEFAULT 'medium',
            sort_order INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
        await self.engine.execute(sql)

    # ========================================================
    #  定时任务表初始化
    # ========================================================

    async def _init_cron_tables(self):
        """初始化 cron_jobs 和 cron_stats 表"""
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            handler_key TEXT NOT NULL,
            interval_sec INTEGER NOT NULL DEFAULT 3600,
            cron_expr TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run_at INTEGER DEFAULT 0,
            next_run_at INTEGER DEFAULT 0,
            last_result TEXT DEFAULT '',
            run_count INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS cron_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_key TEXT UNIQUE NOT NULL,
            stat_value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)

    # ========================================================
    #  活跃作者表初始化
    # ========================================================

    async def _init_active_authors_table(self):
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS active_authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            author_avatar TEXT DEFAULT '',
            blog_count INTEGER DEFAULT 0,
            microblog_count INTEGER DEFAULT 0,
            note_count INTEGER DEFAULT 0,
            rank INTEGER DEFAULT 0,
            period TEXT NOT NULL DEFAULT 'hourly',
            updated_at INTEGER NOT NULL
        )
        """)
        # Migration: add per-type columns if missing
        for col in ("blog_count", "microblog_count", "note_count"):
            try:
                await self.engine.execute(f"ALTER TABLE active_authors ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass

    # ========================================================
    #  定时任务 CRUD
    # ========================================================

    async def _list_cron_jobs(self) -> List[Dict]:
        await self._init_cron_tables()
        rows = await self.engine.fetchall(
            "SELECT * FROM cron_jobs ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    async def _get_cron_job(self, job_id: int) -> Optional[Dict]:
        await self._init_cron_tables()
        row = await self.engine.fetchone(
            "SELECT * FROM cron_jobs WHERE id = ?", (job_id,)
        )
        return dict(row) if row else None

    async def _create_cron_job(self, name: str, handler_key: str,
                                interval_sec: int = 3600,
                                cron_expr: str = "",
                                description: str = "") -> int:
        await self._init_cron_tables()
        now = int(time.time())
        row_id = await self.engine.put("cron_jobs", 0, {
            "name": name,
            "description": description,
            "handler_key": handler_key,
            "interval_sec": interval_sec,
            "cron_expr": cron_expr,
            "enabled": 1,
            "last_run_at": 0,
            "next_run_at": now + interval_sec,
            "last_result": "",
            "run_count": 0,
            "created_at": now,
            "updated_at": now,
        })
        return row_id

    async def _update_cron_job(self, job_id: int, data: Dict) -> None:
        await self._init_cron_tables()
        data["updated_at"] = int(time.time())
        await self.engine.put("cron_jobs", job_id, data)

    async def _delete_cron_job(self, job_id: int) -> None:
        await self._init_cron_tables()
        await self.engine.delete("cron_jobs", job_id)

    # ========================================================
    #  定时任务执行
    # ========================================================

    async def _execute_job(self, job: Dict) -> str:
        """执行单个定时任务，返回结果文本"""
        handler_key = job.get("handler_key", "")
        handler = self._handlers.get(handler_key)
        if not handler:
            return f"Unknown handler: {handler_key}"
        try:
            result = await handler()
            return str(result) if result else "OK"
        except Exception as e:
            import traceback
            return f"Error: {e}\n{traceback.format_exc()}"

    async def _update_job_run(self, job_id: int, success: bool, result: str) -> None:
        """更新任务运行结果"""
        now = int(time.time())
        job = await self._get_cron_job(job_id)
        if job:
            run_count = (job.get("run_count") or 0) + 1
            await self.engine.put("cron_jobs", job_id, {
                "last_run_at": now,
                "next_run_at": now + job.get("interval_sec", 3600),
                "last_result": result[:500],   # 截断保存
                "run_count": run_count,
                "enabled": 1,
            })

    async def run_cron_job_api(self, request, **kwargs) -> "HTMLResponse":
        """手动触发执行一个定时任务"""
        from starlette.responses import JSONResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        job_id = int(kwargs.get("job_id", 0))
        job = await self._get_cron_job(job_id)
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)

        result = await self._execute_job(job)
        await self._update_job_run(job_id, True, result)

        return JSONResponse({"success": True, "result": result, "job_id": job_id})

    # ========================================================
    #  任务处理器
    # ========================================================

    async def _handle_stats_collection(self) -> str:
        """统计博客/微博/笔记数量，写入 cron_stats"""
        await self._init_cron_tables()

        # 查询各类型数量
        # 注意：blog/note 用 status='published'，microblog 用 status='public'
        rows = await self.engine.fetchall(
            "SELECT plugin_type, COUNT(*) AS cnt FROM contents WHERE status IN ('published', 'public') GROUP BY plugin_type"
        )
        counts = {r["plugin_type"]: int(r["cnt"]) for r in rows}
        blog_count    = counts.get("blog",       0)
        microblog_count = counts.get("microblog", 0)
        note_count    = counts.get("note",       0)
        total_count   = blog_count + microblog_count + note_count

        now = int(time.time())

        # 写入 cron_stats
        for key, value in [
            ("blog_count",       blog_count),
            ("microblog_count",   microblog_count),
            ("note_count",        note_count),
            ("total_count",       total_count),
            ("stats_updated_at",  now),
        ]:
            # upsert: INSERT OR REPLACE
            await self.engine.execute(
                "INSERT OR REPLACE INTO cron_stats (stat_key, stat_value, updated_at) VALUES (?, ?, ?)",
                (key, str(value), now)
            )

        return (f"博客:{blog_count} "
                f"微博:{microblog_count} "
                f"笔记:{note_count} "
                f"总计:{total_count}")

    async def _handle_active_authors(self) -> str:
        """统计最近 7 天内活跃作者（按内容数量排名），写入 active_authors 表"""
        await self._init_active_authors_table()
        now = int(time.time())
        # 7 天时间窗口
        week_ago = now - 7 * 86400

        rows = await self.engine.fetchall("""
            SELECT c.author_id,
                   u.username AS author_name,
                   u.avatar AS author_avatar,
                   SUM(CASE WHEN c.plugin_type = 'blog' THEN 1 ELSE 0 END) AS blog_count,
                   SUM(CASE WHEN c.plugin_type = 'microblog' THEN 1 ELSE 0 END) AS microblog_count,
                   SUM(CASE WHEN c.plugin_type = 'note' THEN 1 ELSE 0 END) AS note_count,
                   COUNT(*) AS total_count
            FROM contents c
            LEFT JOIN users u ON c.author_id = u.id
            WHERE c.status IN ('published', 'public')
              AND c.author_id IS NOT NULL
              AND c.created_at >= ?
            GROUP BY c.author_id
            ORDER BY total_count DESC
            LIMIT 10
        """, (week_ago,))

        if not rows:
            return "无活跃作者数据"

        lines = []
        for rank, row in enumerate(rows, 1):
            author_id       = int(row["author_id"])
            author_name     = row["author_name"] or "匿名"
            author_avatar   = row["author_avatar"] or ""
            blog_count      = int(row["blog_count"])
            microblog_count = int(row["microblog_count"])
            note_count      = int(row["note_count"])

            await self.engine.execute("""
                INSERT OR REPLACE INTO active_authors
                    (author_id, author_name, author_avatar,
                     blog_count, microblog_count, note_count,
                     "rank", period, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'weekly', ?)
            """, (author_id, author_name, author_avatar,
                  blog_count, microblog_count, note_count,
                  rank, now))
            lines.append(f"{rank}. {author_name} "
                         f"(博客:{blog_count} 微博:{microblog_count} 笔记:{note_count})")

        return "活跃作者: " + ", ".join(lines)

    # ========================================================
    #  公开统计接口（供首页等调用）
    # ========================================================

    async def get_active_authors(self) -> List[Dict[str, Any]]:
        """获取活跃作者列表，优先从 active_authors 读取，否则实时计算"""
        await self._init_active_authors_table()
        now = int(time.time())
        rows = await self.engine.fetchall(
            "SELECT author_name, author_avatar, "
            "blog_count, microblog_count, note_count, updated_at "
            "FROM active_authors WHERE period = 'weekly' "
            "ORDER BY \"rank\" ASC LIMIT 8"
        )
        if not rows:
            return []
        # 检查是否过期（超过 2 小时）
        updated_at = int(rows[0].get("updated_at", 0)) if rows else 0
        if updated_at < now - 7200:
            # 过期了，手动触发一次实时计算（不等待结果）
            try:
                await self._handle_active_authors()
                rows = await self.engine.fetchall(
                    "SELECT author_name, author_avatar, "
                    "blog_count, microblog_count, note_count, updated_at "
                    "FROM active_authors WHERE period = 'weekly' "
                    "ORDER BY \"rank\" ASC LIMIT 8"
                )
            except Exception:
                pass
        return [dict(r) for r in rows]

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计数字，优先从 cron_stats 读取，否则实时查"""
        await self._init_cron_tables()
        rows = await self.engine.fetchall("SELECT stat_key, stat_value FROM cron_stats")
        if rows:
            stats = {r["stat_key"]: r["stat_value"] for r in rows}
            updated_at = int(stats.get("stats_updated_at", 0))
            # 超过 2 小时视为过期，尝试实时计算
            if updated_at < int(time.time()) - 7200:
                return await self._compute_live_stats()
            return {
                "blog_count":    int(stats.get("blog_count", 0)),
                "microblog_count": int(stats.get("microblog_count", 0)),
                "note_count":    int(stats.get("note_count", 0)),
                "total_count":   int(stats.get("total_count", 0)),
                "stats_updated_at": updated_at,
            }
        return await self._compute_live_stats()

    async def _compute_live_stats(self) -> Dict[str, Any]:
        """实时计算统计数字"""
        rows = await self.engine.fetchall(
            "SELECT plugin_type, COUNT(*) AS cnt FROM contents WHERE status='published' GROUP BY plugin_type"
        )
        counts = {r["plugin_type"]: int(r["cnt"]) for r in rows}
        blog_count     = counts.get("blog",       0)
        microblog_count = counts.get("microblog", 0)
        note_count     = counts.get("note",       0)
        return {
            "blog_count":       blog_count,
            "microblog_count":  microblog_count,
            "note_count":       note_count,
            "total_count":      blog_count + microblog_count + note_count,
            "stats_updated_at": int(time.time()),
        }

    # ========================================================
    #  定时任务页面
    # ========================================================

    async def cron_page(self, request, **kwargs):
        """定时任务管理页面"""
        from starlette.responses import HTMLResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        current_user = await self._get_current_user(request)
        jobs = await self._list_cron_jobs()

        html = await self.template_engine.render(
            "board.html",
            {
                "nav_page": "board",
                "section": "cron",
                "current_user": current_user,
                "cron_jobs": jobs,
                "PRESET_JOBS": PRESET_JOBS,
                "INTERVAL_OPTIONS": INTERVAL_OPTIONS,
                "pending_posts": [],
            }
        )
        return HTMLResponse(content=html)

    # ========================================================
    #  定时任务 API
    # ========================================================

    async def list_cron_jobs_api(self, request, **kwargs):
        """GET /board/cron/jobs"""
        from starlette.responses import JSONResponse
        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect
        jobs = await self._list_cron_jobs()
        return JSONResponse({"jobs": jobs})

    async def create_cron_job(self, request, **kwargs):
        """POST /board/cron/jobs"""
        from starlette.responses import JSONResponse, RedirectResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        form = await request.form()
        name = (form.get("name") or "").strip()
        handler_key = (form.get("handler_key") or "").strip()
        description = (form.get("description") or "").strip()
        interval_opt = (form.get("interval_opt") or "hourly").strip()
        redirect_to_page = form.get("_page") == "1"

        if not name or not handler_key:
            if redirect_to_page:
                return RedirectResponse(url="/board/cron", status_code=302)
            return JSONResponse({"error": "name and handler_key required"}, status_code=400)

        # interval 映射
        interval_map = {"hourly": 3600, "daily": 86400, "weekly": 604800}
        interval_sec = interval_map.get(interval_opt, 3600)

        job_id = await self._create_cron_job(
            name=name, handler_key=handler_key,
            interval_sec=interval_sec, description=description
        )

        if redirect_to_page:
            return RedirectResponse(url="/board/cron", status_code=302)
        return JSONResponse({"success": True, "job_id": job_id})

    async def update_cron_job(self, request, **kwargs):
        """PUT /board/cron/jobs/{job_id}"""
        from starlette.responses import JSONResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        job_id = int(kwargs.get("job_id", 0))
        form = await request.form()

        data = {}
        if "name" in form:
            data["name"] = (form.get("name") or "").strip()
        if "description" in form:
            data["description"] = (form.get("description") or "").strip()
        if "enabled" in form:
            data["enabled"] = 1 if form.get("enabled") in ("1", "true", "on") else 0
        if "interval_opt" in form:
            interval_map = {"hourly": 3600, "daily": 86400, "weekly": 604800}
            data["interval_sec"] = interval_map.get(form.get("interval_opt", "hourly"), 3600)

        if data:
            await self._update_cron_job(job_id, data)

        return JSONResponse({"success": True})

    async def delete_cron_job(self, request, **kwargs):
        """DELETE /board/cron/jobs/{job_id}"""
        from starlette.responses import JSONResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        job_id = int(kwargs.get("job_id", 0))
        await self._delete_cron_job(job_id)
        return JSONResponse({"success": True})

    # ========================================================
    #  网站设置
    # ========================================================

    async def settings_page(self, request, **kwargs):
        """网站设置页面"""
        from starlette.responses import HTMLResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        html = await self.template_engine.render(
            "settings.html",
            {"nav_page": "board", "section": "settings"},
        )
        return HTMLResponse(html)

    async def moderation_page(self, request, **kwargs):
        """微博审核页面"""
        from starlette.responses import HTMLResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        # 获取微博插件的待审核列表
        mb_plugin = self.ctx.get_plugin("microblog")
        pending = []
        if mb_plugin:
            pending = await mb_plugin.get_pending_posts()
        return HTMLResponse(
            await self.template_engine.render(
                "moderation.html",
                {
                    "nav_page": "board",
                    "section": "moderation",
                    "pending_posts": pending,
                },
            )
        )

    async def get_settings_api(self, request, **kwargs):
        """GET /board/settings/api - 获取当前设置"""
        from starlette.responses import JSONResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        settings = await self._get_site_settings()
        return JSONResponse(settings)

    async def update_settings_api(self, request, **kwargs):
        """PUT /board/settings/api - 更新设置"""
        from starlette.responses import JSONResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        await self._update_site_settings(data)
        # 清除模板引擎缓存
        if self.template_engine:
            self.template_engine._site_cache = None
        return JSONResponse({"success": True})

    async def _get_site_settings(self) -> Dict[str, str]:
        """从数据库读取网站设置"""
        defaults = {
            "title": "pyWork",
            "logo_text": "pyWork",
            "footer_text": "© 2026 pyWork. All rights reserved.",
            "description": "多用户数字工作台",
            "announcement": "",
        }
        try:
            rows = await self.engine.fetchall("SELECT key, value FROM site_config")
            settings = dict(defaults)
            for row in rows:
                settings[row["key"]] = row["value"]
            return settings
        except Exception:
            return defaults

    async def _update_site_settings(self, data: Dict[str, str]):
        """更新网站设置到数据库"""
        allowed_keys = ["title", "logo_text", "footer_text", "description", "primary_color", "announcement"]
        # 确保表存在
        await self.engine.execute("""
            CREATE TABLE IF NOT EXISTS site_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        for key in allowed_keys:
            if key in data:
                try:
                    # SQLite UPSERT: INSERT OR REPLACE
                    await self.engine.execute(
                        "INSERT OR REPLACE INTO site_config (key, value) VALUES (?, ?)",
                        (key, data[key])
                    )
                except Exception as e:
                    print(f"[Board] Failed to update {key}: {e}")

    # ========================================================
    #  看板页面（整合定时任务）
    # ========================================================

    async def board_page(self, request, **kwargs):
        """看板页面 + 定时任务入口"""
        from starlette.responses import HTMLResponse

        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect

        current_user = await self._get_current_user(request)
        await self._init_board_table()

        # 读取看板任务
        rows = await self.engine.fetchall(
            "SELECT * FROM board_tasks ORDER BY status, sort_order ASC, created_at DESC"
        )
        tasks = [dict(r) for r in rows]

        # 读取定时任务
        cron_jobs = await self._list_cron_jobs()

        # 按状态分组看板任务
        columns = {"todo": [], "in-progress": [], "done": []}
        for task in tasks:
            status = task.get("status", "todo")
            if status in columns:
                columns[status].append(task)

        html = await self.template_engine.render(
            "board.html",
            {
                "nav_page": "board",
                "section": "board",
                "tasks": tasks,
                "columns": columns,
                "current_user": current_user,
                "PRIORITY_LABELS": {
                    "low": "🟢 低",
                    "medium": "🟡 中",
                    "high": "🔴 高",
                },
                "cron_jobs": cron_jobs,
                "PRESET_JOBS": PRESET_JOBS,
                "INTERVAL_OPTIONS": INTERVAL_OPTIONS,
                "pending_posts": [],
            }
        )
        return HTMLResponse(content=html)

    # ========================================================
    #  看板 CRUD
    # ========================================================

    async def create_task(self, request, **kwargs):
        from starlette.responses import RedirectResponse
        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect
        form = await request.form()
        title = (form.get("title") or "").strip()
        description = (form.get("description") or "").strip()
        status = (form.get("status") or "todo").strip()
        priority = (form.get("priority") or "medium").strip()
        if not title:
            return RedirectResponse(url="/board", status_code=302)
        now = int(time.time())
        await self._init_board_table()
        await self.engine.put("board_tasks", 0, {
            "title": title, "description": description,
            "status": status, "priority": priority,
            "created_at": now, "updated_at": now,
        })
        return RedirectResponse(url="/board", status_code=302)

    async def update_task(self, request, **kwargs):
        from starlette.responses import JSONResponse
        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect
        task_id = int(kwargs.get("task_id", 0))
        form = await request.form()
        task = await self.engine.get("board_tasks", task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        for field in ("title", "description", "status", "priority"):
            if field in form:
                task[field] = (form.get(field) or "").strip()
        if "assignee_id" in form:
            task["assignee_id"] = int(form.get("assignee_id") or 0) or None
            task["assignee_name"] = (form.get("assignee_name") or "").strip()
        task["updated_at"] = int(time.time())
        await self.engine.put("board_tasks", task_id, task)
        return JSONResponse({"success": True, "task": task})

    async def delete_task(self, request, **kwargs):
        from starlette.responses import JSONResponse
        redirect = await self._check_admin_or_redirect(request)
        if redirect:
            return redirect
        task_id = int(kwargs.get("task_id", 0))
        await self.engine.delete("board_tasks", task_id)
        return JSONResponse({"success": True})
