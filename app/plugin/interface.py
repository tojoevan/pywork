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
    handler: Callable[..., Any]


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
