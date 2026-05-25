"""
主题切换插件 - 支持用户在传统界面和 V7.1 极简界面之间切换
"""
import json
import time
from typing import Optional, Dict, Any, List
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from app.plugin import Plugin, PluginContext, Route
from app.log import get_logger

log = get_logger("theme_switcher")


class ThemeSwitcherPlugin(Plugin):
    """主题切换插件"""
    
    def __init__(self):
        self.engine = None
        self.config = None
    
    @property
    def name(self) -> str:
        return "theme_switcher"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    async def init(self, ctx: PluginContext):
        """初始化插件"""
        self.engine = ctx.engine
        self.config = ctx.config
        self._ctx = ctx
        
        # 创建 user_preferences 表（如果不存在）
        await self._init_user_preferences_table()
    
    async def _init_user_preferences_table(self):
        """创建用户偏好设置表"""
        await self.engine.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                theme_preference TEXT NOT NULL DEFAULT 'traditional',
                language_preference TEXT NOT NULL DEFAULT 'zh-CN',
                updated_at INTEGER NOT NULL
            )
        """)
    
    def routes(self) -> List[Route]:
        """定义 HTTP 路由"""
        return [
            Route(path="/api/theme/preference", method="GET", handler=self.get_theme_preference),
            Route(path="/api/theme/preference", method="POST", handler=self.set_theme_preference),
            Route(path="/v7", method="GET", handler=self.v7_dashboard),
        ]
    
    async def get_theme_preference(self, request):
        """获取用户的主题偏好"""
        auth_plugin = self._ctx.get_plugin("auth")
        if not auth_plugin:
            return JSONResponse({"error": "Auth plugin not available"}, status_code=503)
        
        user = await self.get_current_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        
        # 查询用户偏好
        row = await self.engine.fetchone(
            "SELECT theme_preference, language_preference FROM user_preferences WHERE user_id = ?",
            (user["id"],)
        )
        
        if row:
            return JSONResponse({
                "theme": row["theme_preference"],
                "language": row["language_preference"]
            })
        else:
            # 返回默认值
            return JSONResponse({
                "theme": "traditional",
                "language": "zh-CN"
            })
    
    async def set_theme_preference(self, request, **kwargs):
        """设置用户的主题偏好"""
        auth_plugin = self._ctx.get_plugin("auth")
        if not auth_plugin:
            return JSONResponse({"error": "Auth plugin not available"}, status_code=503)
        
        user = await self.get_current_user(request)
        if not user:
            return JSONResponse({"error": "Not authenticated"}, status_code=401)
        
        try:
            body = await request.json()
            theme = body.get("theme", "traditional")
            language = body.get("language", "zh-CN")
            
            # 验证主题值
            if theme not in ["traditional", "v7"]:
                return JSONResponse({"error": "Invalid theme value"}, status_code=400)
            
            # 验证语言值
            if language not in ["zh-CN", "en-US"]:
                return JSONResponse({"error": "Invalid language value"}, status_code=400)
            
            now = int(time.time())
            
            # 检查是否已存在记录
            existing = await self.engine.fetchone(
                "SELECT user_id FROM user_preferences WHERE user_id = ?",
                (user["id"],)
            )
            
            if existing:
                # 更新现有记录
                await self.engine.execute(
                    "UPDATE user_preferences SET theme_preference = ?, language_preference = ?, updated_at = ? WHERE user_id = ?",
                    (theme, language, now, user["id"])
                )
            else:
                # 插入新记录
                await self.engine.execute(
                    "INSERT INTO user_preferences (user_id, theme_preference, language_preference, updated_at) VALUES (?, ?, ?, ?)",
                    (user["id"], theme, language, now)
                )
            
            log.info(f"User {user['username']} updated theme preference to {theme}, language to {language}")
            
            return JSONResponse({
                "success": True,
                "theme": theme,
                "language": language
            })
        
        except Exception as e:
            log.error(f"Error setting theme preference: {e}")
            return JSONResponse({"error": "Internal server error"}, status_code=500)
    
    async def v7_dashboard(self, request):
        """V7.1 极简仪表盘页面"""
        auth_plugin = self._ctx.get_plugin("auth")
        if not auth_plugin:
            return HTMLResponse(content="<h1>Auth plugin not available</h1>", status_code=503)

        user = await self.get_current_user(request)
        if not user:
            return RedirectResponse(url="/login", status_code=302)

        import os
        template_path = os.path.join(os.path.dirname(__file__), "templates", "v7_dashboard.html")

        if not os.path.exists(template_path):
            return HTMLResponse(content="<h1>V7 Dashboard template not found</h1>", status_code=500)

        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # 获取用户语言偏好
        user_lang = "cn"
        lang_pref = await self.get_user_language(user["id"])
        if lang_pref == "en-US":
            user_lang = "en"

        # 获取统计数据
        stats = await self._get_dashboard_stats()

        # 获取最近动态
        recent_items = await self._get_recent_activity(limit=15)

        # 替换占位符
        site_title = getattr(self.config, 'title', 'pyWork') or 'pyWork'
        html_content = html_content.replace("{{ username }}", user.get("username", "User"))
        html_content = html_content.replace("{{ display_name }}", user.get("display_name") or user.get("nickname") or user.get("username", "User"))
        html_content = html_content.replace('{{ user_lang | default("cn") }}', user_lang)
        html_content = html_content.replace('{{ site_title }}', site_title)

        # 替换统计数据
        html_content = html_content.replace('{{ total_posts }}', str(stats["total_posts"]))
        html_content = html_content.replace('{{ total_notes }}', str(stats["total_notes"]))
        html_content = html_content.replace('{{ total_microblogs }}', str(stats["total_microblogs"]))
        html_content = html_content.replace('{{ total_users }}', str(stats["total_users"]))
        html_content = html_content.replace('{{ draft_count }}', str(stats["draft_count"]))
        html_content = html_content.replace('{{ comment_count }}', str(stats["comment_count"]))

        # 替换动态列表
        activity_html = self._render_activity_items(recent_items)
        html_content = html_content.replace('{{ activity_items }}', activity_html)

        return HTMLResponse(content=html_content)

    async def _get_dashboard_stats(self) -> dict:
        """获取仪表盘统计数据"""
        stats = {
            "total_posts": 0,
            "total_notes": 0,
            "total_microblogs": 0,
            "total_users": 0,
            "draft_count": 0,
            "comment_count": 0,
        }

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM blog_posts")
            stats["total_posts"] = row["cnt"] if row else 0
        except Exception:
            pass

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM notes")
            stats["total_notes"] = row["cnt"] if row else 0
        except Exception:
            pass

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM microblog_posts")
            stats["total_microblogs"] = row["cnt"] if row else 0
        except Exception:
            pass

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM users")
            stats["total_users"] = row["cnt"] if row else 0
        except Exception:
            pass

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM blog_posts WHERE status = 'draft'")
            stats["draft_count"] = row["cnt"] if row else 0
        except Exception:
            pass

        try:
            row = await self.engine.fetchone("SELECT COUNT(*) as cnt FROM comments")
            stats["comment_count"] = row["cnt"] if row else 0
        except Exception:
            pass

        return stats

    async def _get_recent_activity(self, limit: int = 15) -> list:
        """获取最近动态（博客、微博、笔记混合）"""
        items = []

        # 博客
        try:
            rows = await self.engine.fetchall(
                "SELECT id, title, status, created_at FROM blog_posts ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            for row in rows:
                items.append({
                    "type": "BLOG",
                    "id": row["id"],
                    "title": row["title"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "link": f"/blog/view/{row['id']}",
                })
        except Exception:
            pass

        # 微博
        try:
            rows = await self.engine.fetchall(
                "SELECT id, content, created_at FROM microblog_posts ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            for row in rows:
                items.append({
                    "type": "WEIBO",
                    "id": row["id"],
                    "title": row["content"][:60],
                    "status": "published",
                    "created_at": row["created_at"],
                    "link": "/microblog",
                })
        except Exception:
            pass

        # 笔记
        try:
            rows = await self.engine.fetchall(
                "SELECT id, title, visibility, created_at FROM notes ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            for row in rows:
                items.append({
                    "type": "NOTE",
                    "id": row["id"],
                    "title": row["title"] or "无标题",
                    "status": row["visibility"],
                    "created_at": row["created_at"],
                    "link": f"/notes/{row['id']}",
                })
        except Exception:
            pass

        # 按时间排序
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[:limit]

    def _render_activity_items(self, items: list) -> str:
        """渲染动态列表 HTML"""
        if not items:
            return '<div class="stream-item"><div class="item-time">-</div><div class="item-type">-</div><div class="item-title">暂无数据</div><div class="item-status">-</div></div>'

        html_parts = []
        for item in items:
            time_str = self._format_time(item["created_at"])
            status_html = self._format_status(item["status"])
            title_escaped = item["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

            html_parts.append(
                f'<a href="{item["link"]}" class="stream-item">'
                f'<div class="item-time">{time_str}</div>'
                f'<div class="item-type">{item["type"]}</div>'
                f'<div class="item-title">{title_escaped}</div>'
                f'<div class="item-status">{status_html}</div>'
                f'</a>'
            )

        return "\n            ".join(html_parts)

    def _format_time(self, timestamp: int) -> str:
        """格式化时间戳"""
        if not timestamp:
            return "-"
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=8)))
        now = datetime.now(tz=timezone(timedelta(hours=8)))
        delta = now - dt

        if delta.days == 0:
            return dt.strftime("%H:%M")
        elif delta.days == 1:
            return "昨天"
        elif delta.days < 7:
            return f"{delta.days}天前"
        else:
            return dt.strftime("%m/%d")

    def _format_status(self, status: str) -> str:
        """格式化状态显示"""
        if status == "public" or status == "published":
            return '<span class="status-dot"></span>已发布'
        elif status == "draft":
            return "草稿"
        elif status == "private":
            return "私密"
        else:
            return status
    
    async def get_user_theme(self, user_id: int) -> str:
        """获取用户的主题偏好（供其他插件调用）"""
        row = await self.engine.fetchone(
            "SELECT theme_preference FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )
        return row["theme_preference"] if row else "traditional"
    
    async def get_user_language(self, user_id: int) -> str:
        """获取用户的语言偏好（供其他插件调用）"""
        row = await self.engine.fetchone(
            "SELECT language_preference FROM user_preferences WHERE user_id = ?",
            (user_id,)
        )
        return row["language_preference"] if row else "zh-CN"
