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
            # 未登录用户重定向到登录页
            return RedirectResponse(url="/login", status_code=302)
        
        # 读取 V7.1 模板文件
        import os
        template_path = os.path.join(os.path.dirname(__file__), "templates", "v7_dashboard.html")
        
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # 获取用户语言偏好
            user_lang = "cn"  # 默认中文
            lang_pref = await self.get_user_language(user["id"])
            if lang_pref == "en-US":
                user_lang = "en"

            # 替换占位符
            site_title = getattr(self.config, 'title', 'pyWork') or 'pyWork'
            html_content = html_content.replace("{{ username }}", user.get("username", "User"))
            html_content = html_content.replace("{{ display_name }}", user.get("display_name") or user.get("nickname") or user.get("username", "User"))
            html_content = html_content.replace('{{ user_lang | default("cn") }}', user_lang)
            html_content = html_content.replace('{{ site_title }}', site_title)

            return HTMLResponse(content=html_content)
        else:
            return HTMLResponse(content="<h1>V7 Dashboard template not found</h1>", status_code=500)
    
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
