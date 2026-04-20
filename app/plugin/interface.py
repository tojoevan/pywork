"""Plugin system"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
import importlib
import os
import sys

from app.storage import Engine


@dataclass
class MCPTool:
    """MCP tool definition"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any] = None  # Optional; plugin can use mcp_call instead


@dataclass
class MCPResource:
    """MCP resource definition"""
    uri: str
    name: str
    mime_type: str
    handler: Callable[..., Any]


@dataclass
class MCPPrompt:
    """MCP prompt template"""
    name: str
    description: str
    template: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Route:
    """HTTP route definition"""
    path: str
    method: str  # GET | POST | PUT | DELETE
    handler: Callable
    name: Optional[str] = None


@dataclass
class TemplateSet:
    """Template set for plugin"""
    name: str
    files: Dict[str, bytes]  # path -> content
    preview: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


class PluginContext:
    """Plugin context with dependencies"""

    def __init__(self, engine: Engine, config: Dict[str, Any], plugin_manager=None, template_engine=None):
        self.engine = engine
        self.config = config
        self._plugin_manager = plugin_manager
        self.template_engine = template_engine

    def get_plugin(self, name: str) -> Optional[Any]:
        """Get another plugin by name"""
        if self._plugin_manager:
            return self._plugin_manager.plugins.get(name)
        return None


class Plugin(ABC):
    """Plugin base class"""
    
    def __init__(self):
        self._ctx: PluginContext = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name"""
        pass
    
    @property
    def version(self) -> str:
        """Plugin version"""
        return "1.0.0"
    
    @property
    def dependencies(self) -> List[str]:
        """Plugin dependencies"""
        return []
    
    @abstractmethod
    async def init(self, ctx: PluginContext) -> None:
        """Initialize plugin"""
        pass
    
    # ========================================================
    #  通用鉴权方法
    # ========================================================
    
    async def get_current_user(self, request) -> Optional[Dict]:
        """从 HTTP 请求 cookie 或 Authorization header 中获取当前用户"""
        token = request.cookies.get("auth_token", "")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            return None
        auth = self._ctx.get_plugin("auth") if self._ctx else None
        if not auth:
            return None
        return await auth.get_user_by_token(token)
    
    async def get_current_user_mcp(self, mcp_token: str = None) -> Optional[Dict]:
        """从 MCP token 中获取当前用户"""
        if not mcp_token:
            return None
        auth = self._ctx.get_plugin("auth") if self._ctx else None
        if not auth:
            return None
        return await auth.get_user_by_mcp_token(mcp_token)
    
    async def is_admin(self, request) -> bool:
        """检查当前用户是否为管理员"""
        user = await self.get_current_user(request)
        return user is not None and user.get("role") == "admin"
    
    async def require_admin(self, request):
        """要求管理员权限，否则返回 403 JSON 响应"""
        if not await self.is_admin(request):
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return None
    
    async def require_admin_or_redirect(self, request):
        """要求管理员权限，否则重定向到首页"""
        if not await self.is_admin(request):
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/", status_code=302)
        return None
    
    async def require_login_or_redirect(self, request):
        """要求登录，否则重定向到首页"""
        user = await self.get_current_user(request)
        if not user:
            from starlette.responses import RedirectResponse
            return RedirectResponse(url="/", status_code=302)
        return None
    
    # ========================================================
    #  统一错误响应
    # ========================================================
    
    def error_json(self, message: str, status_code: int = 400):
        """返回统一格式的 JSON 错误响应（用于 API handler）"""
        from starlette.responses import JSONResponse
        return JSONResponse({"error": message}, status_code=status_code)
    
    def error_html(self, message: str, status_code: int = 400):
        """返回统一格式的 HTML 错误页面（用于页面 handler）"""
        from starlette.responses import HTMLResponse
        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{status_code}</title>
<style>
body{{font-family:-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f5f5f5;color:#333}}
.card{{background:#fff;border-radius:8px;padding:2rem 3rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}}
h1{{margin:0 0 .5rem;font-size:3rem;color:#e74c3c}}
p{{margin:0 0 1.5rem;color:#666}}
a{{color:#3498db;text-decoration:none}}a:hover{{text-decoration:underline}}
</style></head>
<body><div class="card"><h1>{status_code}</h1><p>{message}</p><a href="/">← 返回首页</a></div></body></html>'''
        return HTMLResponse(content=html, status_code=status_code)
    
    @abstractmethod
    def routes(self) -> List[Route]:
        """HTTP routes"""
        pass
    
    def mcp_tools(self) -> List[MCPTool]:
        """MCP tools"""
        return []
    
    def mcp_resources(self) -> List[MCPResource]:
        """MCP resources"""
        return []
    
    def mcp_prompts(self) -> List[MCPPrompt]:
        """MCP prompts"""
        return []
    
    def templates(self) -> List[TemplateSet]:
        """Template sets"""
        return []
    
    async def shutdown(self) -> None:
        """Cleanup"""
        pass


class PluginManager:
    """Plugin manager"""
    
    def __init__(self, engine: Engine, plugin_dir: str = "./plugins"):
        self.engine = engine
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Plugin] = {}
        self.contexts: Dict[str, PluginContext] = {}
    
    async def load_plugin(self, name: str, config: Optional[Dict[str, Any]] = None) -> Plugin:
        """Load a plugin by name"""
        if name in self.plugins:
            return self.plugins[name]
        
        # Try to import from plugin directory
        plugin_path = os.path.join(self.plugin_dir, name)
        if os.path.exists(plugin_path):
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)
        
        # Import the plugin module
        module_name = f"plugins.{name}"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            module = importlib.import_module(name)
        
        # Find Plugin subclass
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                plugin_class = attr
                break
        
        if not plugin_class:
            raise ValueError(f"No Plugin class found in {module_name}")
        
        # Instantiate and initialize
        plugin = plugin_class()
        template_engine = getattr(self, '_template_engine', None)
        ctx = PluginContext(engine=self.engine, config=config or {}, plugin_manager=self, template_engine=template_engine)

        await plugin.init(ctx)
        
        self.plugins[name] = plugin
        self.contexts[name] = ctx
        
        return plugin
    
    async def load_all(self, enabled: List[str], configs: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """Load all enabled plugins"""
        configs = configs or {}
        for name in enabled:
            await self.load_plugin(name, configs.get(name))
    
    def get_plugin(self, name: str) -> Plugin:
        """Get loaded plugin"""
        return self.plugins[name]
    
    def get_enabled_plugins(self) -> List[Plugin]:
        """Get all enabled plugins"""
        return list(self.plugins.values())
    
    def get_all_tools(self) -> List[tuple]:
        """Get all MCP tools from all plugins"""
        tools = []
        for plugin in self.plugins.values():
            for tool in plugin.mcp_tools():
                tools.append((plugin.name, tool))
        return tools
    
    def get_all_resources(self) -> List[tuple]:
        """Get all MCP resources from all plugins"""
        resources = []
        for plugin in self.plugins.values():
            for resource in plugin.mcp_resources():
                resources.append((plugin.name, resource))
        return resources
    
    def get_all_prompts(self) -> List[tuple]:
        """Get all MCP prompts from all plugins"""
        prompts = []
        for plugin in self.plugins.values():
            for prompt in plugin.mcp_prompts():
                prompts.append((plugin.name, prompt))
        return prompts
    
    async def shutdown_all(self) -> None:
        """Shutdown all plugins"""
        for plugin in self.plugins.values():
            await plugin.shutdown()
