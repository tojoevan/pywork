"""MCP server implementation"""
import asyncio
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from app.plugin import PluginManager


@dataclass
class TextContent:
    """Text content type"""
    type: str = "text"
    text: str = ""


class WorkbenchMCPServer:
    """Minimal MCP server for pyWork"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._handlers: Dict[str, Callable] = {}
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP handlers"""
        
        self._handlers["tools/list"] = self._list_tools
        self._handlers["tools/call"] = self._call_tool
        self._handlers["resources/list"] = self._list_resources
        self._handlers["resources/read"] = self._read_resource
        self._handlers["prompts/list"] = self._list_prompts
        self._handlers["prompts/get"] = self._get_prompt
        self._handlers["initialize"] = self._initialize
    
    async def handle(self, method: str, params: Dict[str, Any]) -> Any:
        """Handle MCP request"""
        handler = self._handlers.get(method)
        if not handler:
            raise ValueError(f"Unknown method: {method}")
        
        return await handler(params)
    
    async def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize handshake"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {}
            },
            "serverInfo": {
                "name": "pyWork",
                "version": "0.1.0"
            }
        }
    
    async def _list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all tools"""
        tools = []
        for plugin_name, tool in self.plugin_manager.get_all_tools():
            tools.append({
                "name": f"{plugin_name}.{tool.name}",
                "description": tool.description,
                "inputSchema": tool.input_schema
            })
        
        return {"tools": tools}
    
    async def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        meta = params.get("meta", {})  # MCP meta 包含 token 等信息
        mcp_token = meta.get("token", "")

        # Parse plugin.tool
        parts = name.split(".", 1)
        if len(parts) != 2:
            return {"content": [TextContent(text="Invalid tool name").__dict__]}

        plugin_name, tool_name = parts

        # Find the tool
        for plugin in self.plugin_manager.get_enabled_plugins():
            if plugin.name == plugin_name:
                for tool in plugin.mcp_tools():
                    if tool.name == tool_name:
                        try:
                            # 传递 mcp_token 给插件进行认证
                            if hasattr(plugin, 'mcp_call'):
                                result = await plugin.mcp_call(tool_name, arguments, mcp_token)
                            else:
                                result = await tool.handler(**arguments)
                            return {
                                "content": [
                                    TextContent(
                                        type="text",
                                        text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
                                    ).__dict__
                                ]
                            }
                        except Exception as e:
                            return {
                                "content": [TextContent(type="text", text=f"Error: {e}").__dict__],
                                "isError": True
                            }

        return {"content": [TextContent(text=f"Tool not found: {name}").__dict__]}
    
    async def _list_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all resources"""
        resources = []
        for plugin_name, resource in self.plugin_manager.get_all_resources():
            resources.append({
                "uri": resource.uri,
                "name": resource.name,
                "mimeType": resource.mime_type
            })
        
        return {"resources": resources}
    
    async def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a resource"""
        uri = params.get("uri", "")
        
        # Parse URI: plugin://resource_type/args
        parts = uri.split("://", 1)
        if len(parts) != 2:
            return {"contents": [{"uri": uri, "text": "Invalid URI"}]}
        
        plugin_name = parts[0]
        resource_path = parts[1]
        
        for plugin in self.plugin_manager.get_enabled_plugins():
            if plugin.name == plugin_name:
                for resource in plugin.mcp_resources():
                    if resource.uri == uri or uri.startswith(resource.uri.split("{")[0]):
                        try:
                            result = await resource.handler()
                            return {
                                "contents": [{
                                    "uri": uri,
                                    "mimeType": resource.mime_type,
                                    "text": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                                }]
                            }
                        except Exception as e:
                            return {"contents": [{"uri": uri, "text": f"Error: {e}"}]}
        
        return {"contents": [{"uri": uri, "text": f"Resource not found: {uri}"}]}
    
    async def _list_prompts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all prompts"""
        prompts = []
        for plugin_name, prompt in self.plugin_manager.get_all_prompts():
            prompts.append({
                "name": f"{plugin_name}.{prompt.name}",
                "description": prompt.description,
                "arguments": prompt.arguments
            })
        
        return {"prompts": prompts}
    
    async def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a prompt"""
        name = params.get("name", "")
        
        parts = name.split(".", 1)
        if len(parts) != 2:
            return {"description": "Invalid prompt name", "messages": []}
        
        plugin_name, prompt_name = parts
        
        for plugin in self.plugin_manager.get_enabled_plugins():
            if plugin.name == plugin_name:
                for prompt in plugin.mcp_prompts():
                    if prompt.name == prompt_name:
                        # Simple template substitution
                        template = prompt.template
                        args = params.get("arguments", {})
                        
                        for key, value in args.items():
                            template = template.replace("{{" + key + "}}", str(value))
                        
                        return {
                            "description": prompt.description,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": {"type": "text", "text": template}
                                }
                            ]
                        }
        
        return {"description": "Prompt not found", "messages": []}
    
    async def run_stdio(self):
        """Run MCP server in stdio mode"""
        import sys
        
        reader = asyncio.StreamReader()
        reader_protocol = asyncio.StreamReaderProtocol(reader)
        
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)
        
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            lambda: asyncio.streams.FlowControlMixin(),
            sys.stdout
        )
        writer = asyncio.streams.StreamWriter(writer_transport, writer_protocol, reader, loop)
        
        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                
                # Parse JSON-RPC
                request = json.loads(line.decode('utf-8'))
                method = request.get("method", "")
                params = request.get("params", {})
                request_id = request.get("id")
                
                # Handle request
                try:
                    result = await self.handle(method, params)
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": result
                    }
                except Exception as e:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": str(e)}
                    }
                
                # Write response
                writer.write((json.dumps(response) + "\n").encode('utf-8'))
                await writer.drain()
                
            except Exception as e:
                # Log error and continue
                print(f"Error: {e}", file=sys.stderr)
