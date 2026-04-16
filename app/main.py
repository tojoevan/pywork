"""Main application entry point"""
import asyncio
import argparse
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from app.storage import SQLiteEngine
from app.plugin import PluginManager
from app.mcp import WorkbenchMCPServer


class WorkbenchApp:
    """Main application"""
    
    def __init__(
        self,
        db_path: str = "./data/pywork.db",
        plugin_dir: str = "./plugins",
        enabled_plugins: Optional[list] = None
    ):
        self.db_path = db_path
        self.plugin_dir = plugin_dir
        self.enabled_plugins = enabled_plugins or ["blog"]
        
        self.engine = SQLiteEngine(db_path)
        self.plugin_manager = PluginManager(self.engine, plugin_dir)
        self.mcp_server: Optional[WorkbenchMCPServer] = None
        
        self.app = FastAPI(
            title="pyWork",
            description="Multi-user digital workbench with MCP integration",
            version="0.1.0"
        )
    
    async def startup(self):
        """Startup application"""
        # Start storage engine
        await self.engine.start()
        print(f"✓ SQLite engine started: {self.db_path}")
        
        # Load plugins
        await self.plugin_manager.load_all(self.enabled_plugins)
        print(f"✓ Plugins loaded: {list(self.plugin_manager.plugins.keys())}")
        
        # Setup MCP server
        self.mcp_server = WorkbenchMCPServer(self.plugin_manager)
        
        # Setup routes
        self._setup_routes()
    
    async def shutdown(self):
        """Shutdown application"""
        await self.plugin_manager.shutdown_all()
        await self.engine.stop()
        print("✓ Shutdown complete")
    
    def _setup_routes(self):
        """Setup HTTP routes from plugins"""
        
        @self.app.get("/")
        async def root():
            return {
                "name": "pyWork",
                "version": "0.1.0",
                "plugins": list(self.plugin_manager.plugins.keys())
            }
        
        @self.app.get("/health")
        async def health():
            return {"status": "ok"}
        
        # Register plugin routes
        for plugin in self.plugin_manager.get_enabled_plugins():
            for route in plugin.routes():
                # Register route dynamically
                self._register_route(route)
    
    def _register_route(self, route):
        """Register a single route"""
        
        if route.method in ("POST", "PUT"):
            async def post_handler(request: Request):
                body = await request.json()
                # Merge path params into body
                params = dict(request.path_params)
                params.update(body)
                return await route.handler(**params)
            self.app.add_api_route(
                route.path,
                post_handler,
                methods=[route.method],
                name=route.name or f"{route.path}_{id(route)}"
            )
        else:
            async def get_handler(request: Request):
                params = dict(request.path_params)
                params.update(dict(request.query_params))
                if params:
                    return await route.handler(**params)
                else:
                    return await route.handler()
            self.app.add_api_route(
                route.path,
                get_handler,
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
    parser.add_argument("--enabled", default="blog", help="Enabled plugins (comma-separated)")
    parser.add_argument("--http", action="store_true", help="Run HTTP server")
    parser.add_argument("--mcp-stdio", action="store_true", help="Run MCP stdio server")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    
    args = parser.parse_args()
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    
    # Parse enabled plugins
    enabled_plugins = [p.strip() for p in args.enabled.split(",")]
    
    # Create app
    app = WorkbenchApp(
        db_path=args.db,
        plugin_dir=args.plugins,
        enabled_plugins=enabled_plugins
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
