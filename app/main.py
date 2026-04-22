"""Main application entry point"""
import asyncio
import argparse
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.storage import SQLiteEngine
from app.plugin import PluginManager
from app.mcp import WorkbenchMCPServer
from app.template import TemplateEngine
from app.log import setup_logging, get_logger
from app.config import build_config, AppConfig, SiteConfigManager, config_to_dict
from app.services.home_service import HomeService

# 模块级 logger
log = get_logger(__name__, "core")


class WorkbenchApp:
    """Main application"""

    def __init__(
        self,
        db_path: str = "./data/pywork.db",
        plugin_dir: str = "./plugins",
        enabled_plugins: Optional[list] = None,
        template_dir: str = "./templates",
        static_dir: str = "./static",
        config: Optional[AppConfig] = None,
    ):
        self.db_path = db_path
        self.plugin_dir = plugin_dir
        self.enabled_plugins = enabled_plugins or ["blog", "auth", "microblog", "about", "notes", "board"]
        self.template_dir = template_dir
        self.static_dir = static_dir

        self.engine = SQLiteEngine(db_path)
        self.plugin_manager = PluginManager(self.engine, plugin_dir)
        self.template_engine: Optional[TemplateEngine] = None
        self.mcp_server: Optional[WorkbenchMCPServer] = None
        self.site_config_manager = SiteConfigManager(self.engine)
        self.home_service: Optional[HomeService] = None

        # Config: 优先使用传入的 config，否则延迟到 startup 从 DB 构建
        self._config = config
        self._config_built = config is not None

        self.app = FastAPI(
            title="pyWork",
            description="Multi-user digital workbench with MCP integration",
            version="0.1.0"
        )

    async def startup(self):
        """Startup application"""
        # Start storage engine (先启动 DB，config 需要读取 site_config 表)
        await self.engine.start()
        log.info(f"SQLite engine started: {self.db_path}")

        # 构建 AppConfig（从 site_config 表 + 环境变量 + 默认值）
        if not self._config_built:
            self._config = await build_config(engine=self.engine)
            self._config_built = True
        log.info(f"AppConfig loaded: title={self._config.title}, db={self._config.db_path}")

        # 注入 config 到 PluginManager
        self.plugin_manager.config = self._config

        # 初始化日志（data_dir 从 db_path 推导）
        data_dir = os.path.dirname(os.path.abspath(self._config.db_path))
        setup_logging(data_dir=data_dir, log_level=self._config.log_level, engine=self.engine)
        log.info(f"数据目录: {data_dir}")

        # Initialize template engine (pass engine for lazy site config loading)
        self.template_engine = TemplateEngine(self.template_dir, engine=self.engine)

        # Add plugin template directories
        for plugin_name in self.enabled_plugins:
            plugin_tpl_dir = os.path.join(self.plugin_dir, plugin_name, 'templates')
            if os.path.exists(plugin_tpl_dir):
                self.template_engine.add_template_dir(plugin_tpl_dir)
        log.info("Template engine initialized")

        # Load plugins
        log.info(f"Loading plugins: {self.enabled_plugins}")
        self.plugin_manager._template_engine = self.template_engine
        try:
            await self.plugin_manager.load_all(self.enabled_plugins)
        except Exception as e:
            log.exception(f"Plugin load error: {e}")
            raise
        log.info(f"Plugins loaded: {list(self.plugin_manager.plugins.keys())}")

        # Setup MCP server
        self.mcp_server = WorkbenchMCPServer(self.plugin_manager)

        # Initialize HomeService
        self.home_service = HomeService(self.plugin_manager)

        # Setup routes
        self._setup_routes()

        # Mount static files
        if os.path.exists(self.static_dir):
            self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")
            log.info(f"Static files mounted: {self.static_dir}")

    async def shutdown(self):
        """Shutdown application"""
        log.info("pyWork shutting down...")
        await self.plugin_manager.shutdown_all()
        await self.engine.stop()
        log.info("Shutdown complete")

    def _setup_routes(self):
        """Setup HTTP routes from plugins"""

        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """首页"""
            data = await self.home_service.get_home_data()
            html = await self.template_engine.render("home.html", {
                **data,
                "nav_page": "home",
            })
            return HTMLResponse(content=html)

        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        @self.app.get("/api")
        async def api_info():
            """API 信息"""
            return {
                "name": "pyWork",
                "version": "0.1.0",
                "plugins": list(self.plugin_manager.plugins.keys())
            }

        # 博客前端路由
        @self.app.get("/blog", response_class=HTMLResponse)
        async def blog_index(request: Request):
            """博客首页"""
            blog_plugin = self.plugin_manager.plugins.get("blog")
            if blog_plugin:
                page = int(request.query_params.get("page", "1"))
                result = await blog_plugin.search_posts_paginated(page=page, per_page=10)
                html = await self.template_engine.render("index.html", {
                    "posts": result["posts"],
                    "pagination": result["pagination"],
                    "nav_page": "blog"
                })
                return HTMLResponse(content=html)
            return HTMLResponse(content="<h1>Blog plugin not loaded</h1>")

        @self.app.get("/blog/view/{post_id}", response_class=HTMLResponse)
        async def blog_post(request: Request, post_id: int):
            """文章详情页面"""
            blog_plugin = self.plugin_manager.plugins.get("blog")
            auth_plugin = self.plugin_manager.plugins.get("auth")

            # 获取当前用户
            current_user = None
            token = request.cookies.get("auth_token", "")
            if token and auth_plugin:
                current_user = await auth_plugin.get_user_by_token(token)

            if blog_plugin:
                post = await blog_plugin.get_post_api(post_id)
                if post:
                    html = await self.template_engine.render("post.html", {
                        "post": post,
                        "nav_page": "blog",
                        "current_user": current_user
                    })
                    return HTMLResponse(content=html)
            return HTMLResponse(content='<h1>Post not found</h1><p><a href="/">← 返回首页</a></p>', status_code=404)

        # 认证路由
        @self.app.get("/login", response_class=HTMLResponse)
        async def login_page():
            """登录页面"""
            html = await self.template_engine.render("login.html", {"nav_page": ""})
            return HTMLResponse(content=html)

        @self.app.get("/register", response_class=HTMLResponse)
        async def register_page():
            """注册页面"""
            html = await self.template_engine.render("register.html", {"nav_page": ""})
            return HTMLResponse(content=html)

        @self.app.get("/profile", response_class=HTMLResponse)
        async def profile_page():
            """用户中心页面"""
            html = await self.template_engine.render("profile.html", {"nav_page": "profile"})
            return HTMLResponse(content=html)

        @self.app.post("/auth/login")
        async def auth_login(request: Request):
            """登录API"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                return await auth_plugin.login_api(request)
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.post("/auth/register")
        async def auth_register(request: Request):
            """注册API"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                return await auth_plugin.register_api(request)
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.get("/auth/captcha")
        async def auth_captcha():
            """获取验证码"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                return await auth_plugin.captcha_api()
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.post("/auth/logout")
        async def auth_logout(request: Request):
            """登出API"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                return await auth_plugin.logout_api(request)
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.get("/auth/me")
        async def auth_me(request: Request):
            """当前用户"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                result = await auth_plugin.me_api(request)
                if isinstance(result, dict) and result.get("error"):
                    return JSONResponse(result, status_code=401)
                return result
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        # MCP Token 管理路由
        @self.app.get("/auth/mcp-tokens")
        async def list_mcp_tokens(request: Request):
            """获取当前用户的 MCP Token 列表"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if not auth_plugin:
                return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

            # 验证用户登录
            user = await auth_plugin.me_api(request)
            if user.get("error"):
                return JSONResponse({"error": "未登录"}, status_code=401)

            tokens = await auth_plugin.list_mcp_tokens(user["id"])
            return {"tokens": tokens}

        @self.app.post("/auth/mcp-tokens")
        async def create_mcp_token(request: Request):
            """创建新的 MCP Token"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if not auth_plugin:
                return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

            # 验证用户登录
            user = await auth_plugin.me_api(request)
            if user.get("error"):
                return JSONResponse({"error": "未登录"}, status_code=401)

            data = await request.json()
            name = data.get("name", "MCP Client")

            result = await auth_plugin.create_mcp_token(user["id"], name)
            return result

        @self.app.delete("/auth/mcp-tokens/{token_id}")
        async def revoke_mcp_token(request: Request):
            """撤销 MCP Token"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if not auth_plugin:
                return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

            # 验证用户登录
            user = await auth_plugin.me_api(request)
            if user.get("error"):
                return JSONResponse({"error": "未登录"}, status_code=401)

            # 获取 token 前缀(路径参数,8或16位)
            token_prefix = request.path_params.get("token_id", "")
            if not token_prefix:
                return JSONResponse({"error": "缺少 token_id"}, status_code=400)

            # 直接通过 auth plugin 按前缀删除,限制只能删自己的
            ok = await auth_plugin.revoke_mcp_token_by_prefix(user["id"], token_prefix)
            if ok:
                return {"success": True}
            return JSONResponse({"error": "Token 不存在或无权撤销"}, status_code=404)

        # GitHub OAuth 路由
        @self.app.get("/auth/github")
        async def github_auth():
            """GitHub OAuth 授权"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                result = await auth_plugin.github_auth_url_api(type('Request', (), {'query_params': {}})())
                if "url" in result:
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=result["url"])
                return result
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.get("/auth/github/callback")
        async def github_callback(request: Request):
            """GitHub OAuth 回调"""
            auth_plugin = self.plugin_manager.plugins.get("auth")
            if auth_plugin:
                result = await auth_plugin.github_callback_api(request)
                if "success" in result and result.get("success"):
                    # 登录成功,重定向到首页
                    from fastapi.responses import RedirectResponse
                    response = RedirectResponse(url="/", status_code=302)
                    # 设置 cookie
                    response.set_cookie(
                        key="auth_token",
                        value=result.get("token"),
                        httponly=True,
                        max_age=7 * 24 * 3600  # 7天
                    )
                    return response
                if isinstance(result, dict) and result.get("error"):
                    return JSONResponse(result, status_code=400)
                return result
            return JSONResponse({"error": "Auth plugin not loaded"}, status_code=503)

        @self.app.get("/api/mcp-config")
        async def mcp_config(request: Request):
            """获取 MCP 配置(仅 API 模式,不暴露本地路径)"""
            import socket

            # 获取当前主机信息
            hostname = socket.gethostname()

            # 尝试获取实际 IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                local_ip = "127.0.0.1"

            # 检测是否生产环境
            is_production = os.environ.get("PYWORK_ENV") == "production"
            is_docker = os.path.exists("/.dockerenv")

            # 确定基础 URL
            if is_production:
                base_url = os.environ.get("PYWORK_URL", f"https://{hostname}")
            elif is_docker:
                base_url = f"http://{local_ip}:8080"
            else:
                base_url = f"http://localhost:8080"

            # 构建 MCP 配置(仅 API 模式,不暴露任何本地路径或数据库信息)
            config = {
                "mcpServers": {
                    "pywork": {
                        "url": f"{base_url}/mcp",
                        "headers": {
                            "Authorization": "Bearer YOUR_MCP_TOKEN_HERE"
                        }
                    }
                },
                "mcpEnabled": self.mcp_server is not None,
                "environment": {
                    "isProduction": is_production,
                    "baseUrl": base_url
                },
                "note": "请先生成 MCP Token,替换配置中的 YOUR_MCP_TOKEN_HERE"
            }

            return config

        # Register plugin routes
        for plugin in self.plugin_manager.get_enabled_plugins():
            for route in plugin.routes():
                # Register route dynamically
                self._register_route(route)

        # MCP HTTP endpoint
        @self.app.post("/mcp")
        async def mcp_handler(request: Request):
            """MCP HTTP endpoint - receives JSON-RPC requests"""
            body = await request.json()
            method = body.get("method", "")
            params = body.get("params", {})
            request_id = body.get("id")

            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

            # Inject token into params for MCP server
            if token:
                params["meta"] = {"token": token}

            try:
                result = await self.mcp_server.handle(method, params)
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(e)}}

        @self.app.get("/mcp")
        async def mcp_get_handler(request: Request):
            """MCP GET endpoint - for capability discovery"""
            return {"jsonrpc": "2.0", "id": None, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "pyWork", "version": "0.1.0"}
            }}

    def _register_route(self, route):
        """Register a single route

        Note: 使用默认参数 _route=route 进行值捕获,避免闭包引用问题。
        Python 闭包通过引用捕获外层变量,循环中多次调用会导致所有 handler
        共享同一个 route 变量引用,最终全部指向最后一个注册的 route。
        """

        if route.method in ("POST", "PUT"):
            def make_post_handler(r):
                async def post_handler(request: Request):
                    ct = request.headers.get("content-type", "")
                    if "application/json" in ct:
                        body = await request.json()
                    else:
                        # Support form-encoded data
                        try:
                            body = await request.form()
                            body = dict(body)
                        except Exception:
                            body = {}
                    # Merge path params into body
                    params = dict(request.path_params)
                    params.update(body)
                    # Pass request for handlers that need it
                    return await r.handler(request=request, **params)
                return post_handler
            self.app.add_api_route(
                route.path,
                make_post_handler(route),
                methods=[route.method],
                name=route.name or f"{route.path}_{id(route)}"
            )
        else:
            def make_get_handler(r):
                async def get_handler(request: Request):
                    params = dict(request.path_params)
                    params.update(dict(request.query_params))
                    if params:
                        return await r.handler(request=request, **params)
                    else:
                        return await r.handler(request=request)
                return get_handler
            self.app.add_api_route(
                route.path,
                make_get_handler(route),
                methods=[route.method],
                name=route.name or f"{route.path}_{id(route)}"
            )

    def run_http(self, host: str = "0.0.0.0", port: int = 8080):
        """Run HTTP server"""

        @self.app.on_event("startup")
        async def on_startup():
            await self.startup()

        @self.app.on_event("shutdown")
        async def on_shutdown():
            await self.shutdown()

        uvicorn.run(self.app, host=host, port=port)

    async def run_mcp_stdio(self):
        """Run MCP server in stdio mode"""
        await self.startup()
        try:
            await self.mcp_server.run_stdio()
        finally:
            await self.shutdown()


def cli():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="pyWork - Digital Workbench")
    parser.add_argument("--db", default="./data/pywork.db", help="Database path")
    parser.add_argument("--plugins", default="./plugins", help="Plugin directory")
    parser.add_argument("--enabled", default="blog,auth,microblog,about,notes,board", help="Enabled plugins (comma-separated)")
    parser.add_argument("--templates", default="./templates", help="Template directory")
    parser.add_argument("--static", default="./static", help="Static files directory")
    parser.add_argument("--http", action="store_true", help="Run HTTP server")
    parser.add_argument("--mcp-stdio", action="store_true", help="Run MCP stdio server")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")

    args = parser.parse_args()

    # Ensure data directory exists
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)

    # Parse enabled plugins
    enabled_plugins = [p.strip() for p in args.enabled.split(",")]

    # Create app
    app = WorkbenchApp(
        db_path=args.db,
        plugin_dir=args.plugins,
        enabled_plugins=enabled_plugins,
        template_dir=args.templates,
        static_dir=args.static
    )

    if args.mcp_stdio:
        # Run MCP stdio
        asyncio.run(app.run_mcp_stdio())
    elif args.http:
        # Run HTTP server
        app.run_http(host=args.host, port=args.port)
    else:
        # Default: run HTTP
        app.run_http(host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
