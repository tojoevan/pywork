"""Plugin system package"""
from .interface import (
    Plugin, PluginContext, PluginManager,
    MCPTool, MCPResource, MCPPrompt,
    Route, TemplateSet
)

__all__ = [
    'Plugin', 'PluginContext', 'PluginManager',
    'MCPTool', 'MCPResource', 'MCPPrompt',
    'Route', 'TemplateSet'
]
