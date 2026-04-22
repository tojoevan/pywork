"""MCP protocol tests for pyWork

Tests cover:
- Initialize handshake
- Tools list/call
- Resources list/read
- Prompts list/get
- Error handling
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, Any, List, Callable

# ============================================================
#  Mock structures (avoid importing real app modules)
# ============================================================

@dataclass
class MockMCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable = None


@dataclass
class MockMCPResource:
    uri: str
    name: str
    mime_type: str
    handler: Callable


@dataclass
class MockMCPPrompt:
    name: str
    description: str
    template: str
    arguments: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = []


class MockPlugin:
    """Mock plugin with MCP tools/resources/prompts"""

    def __init__(self, name: str):
        self.name = name
        self._mcp_tools = []
        self._mcp_resources = []
        self._mcp_prompts = []

    def add_tool(self, name: str, description: str, input_schema: dict, handler=None):
        self._mcp_tools.append(MockMCPTool(name, description, input_schema, handler))

    def add_resource(self, uri: str, name: str, mime_type: str, handler):
        self._mcp_resources.append(MockMCPResource(uri, name, mime_type, handler))

    def add_prompt(self, name: str, description: str, template: str, arguments=None):
        self._mcp_prompts.append(MockMCPPrompt(name, description, template, arguments))

    def mcp_tools(self):
        return self._mcp_tools

    def mcp_resources(self):
        return self._mcp_resources

    def mcp_prompts(self):
        return self._mcp_prompts


class MockPluginManager:
    """Mock PluginManager for MCP server tests"""

    def __init__(self):
        self.plugins: Dict[str, MockPlugin] = {}

    def add_plugin(self, plugin: MockPlugin):
        self.plugins[plugin.name] = plugin

    def get_enabled_plugins(self):
        return list(self.plugins.values())

    def get_all_tools(self):
        tools = []
        for plugin in self.plugins.values():
            for tool in plugin.mcp_tools():
                tools.append((plugin.name, tool))
        return tools

    def get_all_resources(self):
        resources = []
        for plugin in self.plugins.values():
            for resource in plugin.mcp_resources():
                resources.append((plugin.name, resource))
        return resources

    def get_all_prompts(self):
        prompts = []
        for plugin in self.plugins.values():
            for prompt in plugin.mcp_prompts():
                prompts.append((plugin.name, prompt))
        return prompts


# ============================================================
#  Minimal MCP Server (test copy, avoid import)
# ============================================================

@dataclass
class TextContent:
    type: str = "text"
    text: str = ""


class _MCPServer:
    """Minimal MCP server for testing (internal class, not a test)"""

    def __init__(self, plugin_manager):
        self.plugin_manager = plugin_manager
        self._handlers = {}
        self._setup_handlers()

    def _setup_handlers(self):
        self._handlers["tools/list"] = self._list_tools
        self._handlers["tools/call"] = self._call_tool
        self._handlers["resources/list"] = self._list_resources
        self._handlers["resources/read"] = self._read_resource
        self._handlers["prompts/list"] = self._list_prompts
        self._handlers["prompts/get"] = self._get_prompt
        self._handlers["initialize"] = self._initialize

    async def handle(self, method: str, params: Dict[str, Any]) -> Any:
        handler = self._handlers.get(method)
        if not handler:
            raise ValueError(f"Unknown method: {method}")
        return await handler(params)

    async def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
        tools = []
        for plugin_name, tool in self.plugin_manager.get_all_tools():
            tools.append({
                "name": f"{plugin_name}.{tool.name}",
                "description": tool.description,
                "inputSchema": tool.input_schema
            })
        return {"tools": tools}

    async def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import json
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        meta = params.get("meta", {})
        mcp_token = meta.get("token", "")

        parts = name.split(".", 1)
        if len(parts) != 2:
            return {"content": [TextContent(text="Invalid tool name").__dict__]}

        plugin_name, tool_name = parts

        for plugin in self.plugin_manager.get_enabled_plugins():
            if plugin.name == plugin_name:
                for tool in plugin.mcp_tools():
                    if tool.name == tool_name:
                        try:
                            if hasattr(plugin, 'mcp_call'):
                                result = await plugin.mcp_call(tool_name, arguments, mcp_token)
                            elif tool.handler:
                                result = await tool.handler(**arguments)
                            else:
                                result = {"error": "No handler"}
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
        resources = []
        for plugin_name, resource in self.plugin_manager.get_all_resources():
            resources.append({
                "uri": resource.uri,
                "name": resource.name,
                "mimeType": resource.mime_type
            })
        return {"resources": resources}

    async def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import json
        uri = params.get("uri", "")

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
        prompts = []
        for plugin_name, prompt in self.plugin_manager.get_all_prompts():
            prompts.append({
                "name": f"{plugin_name}.{prompt.name}",
                "description": prompt.description,
                "arguments": prompt.arguments
            })
        return {"prompts": prompts}

    async def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")

        parts = name.split(".", 1)
        if len(parts) != 2:
            return {"description": "Invalid prompt name", "messages": []}

        plugin_name, prompt_name = parts

        for plugin in self.plugin_manager.get_enabled_plugins():
            if plugin.name == plugin_name:
                for prompt in plugin.mcp_prompts():
                    if prompt.name == prompt_name:
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


# ============================================================
#  Test Fixtures
# ============================================================

@pytest.fixture
def plugin_manager():
    """Create a mock plugin manager with sample plugins"""
    pm = MockPluginManager()

    # Blog plugin with tools
    blog = MockPlugin("blog")
    blog.add_tool(
        "create_post",
        "Create a new blog post",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["title", "content"]
        }
    )
    blog.add_tool(
        "list_posts",
        "List all blog posts",
        {"type": "object", "properties": {}}
    )
    pm.add_plugin(blog)

    # Notes plugin with resources
    notes = MockPlugin("notes")
    notes.add_resource(
        "notes://recent",
        "Recent Notes",
        "application/json",
        AsyncMock(return_value=[{"id": 1, "title": "Note 1"}])
    )
    pm.add_plugin(notes)

    # Auth plugin with prompts
    auth = MockPlugin("auth")
    auth.add_prompt(
        "login_help",
        "Help with login",
        "To login, use your username and password. Username: {{username}}",
        [{"name": "username", "description": "Username to show", "required": True}]
    )
    pm.add_plugin(auth)

    return pm


@pytest.fixture
def mcp_server(plugin_manager):
    """Create MCP server with mock plugin manager"""
    return _MCPServer(plugin_manager)


# ============================================================
#  Initialize Tests
# ============================================================

class TestInitialize:
    """Tests for MCP initialize handshake"""

    @pytest.mark.asyncio
    async def test_initialize_returns_protocol_version(self, mcp_server):
        """Initialize should return protocol version"""
        result = await mcp_server.handle("initialize", {})

        assert result["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self, mcp_server):
        """Initialize should return server capabilities"""
        result = await mcp_server.handle("initialize", {})

        assert "capabilities" in result
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert "prompts" in result["capabilities"]

    @pytest.mark.asyncio
    async def test_initialize_returns_server_info(self, mcp_server):
        """Initialize should return server info"""
        result = await mcp_server.handle("initialize", {})

        assert result["serverInfo"]["name"] == "pyWork"
        assert result["serverInfo"]["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_initialize_ignores_params(self, mcp_server):
        """Initialize should work with any params"""
        result = await mcp_server.handle("initialize", {"clientInfo": {"name": "test"}})

        assert result["protocolVersion"] == "2024-11-05"


# ============================================================
#  Tools Tests
# ============================================================

class TestToolsList:
    """Tests for tools/list method"""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self, mcp_server):
        """List tools should return all registered tools"""
        result = await mcp_server.handle("tools/list", {})

        assert "tools" in result
        assert len(result["tools"]) == 2  # blog.create_post, blog.list_posts

    @pytest.mark.asyncio
    async def test_list_tools_namespaced(self, mcp_server):
        """Tools should be namespaced with plugin name"""
        result = await mcp_server.handle("tools/list", {})

        tool_names = [t["name"] for t in result["tools"]]
        assert "blog.create_post" in tool_names
        assert "blog.list_post" in tool_names or "blog.list_posts" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_schema(self, mcp_server):
        """Tools should include input schema"""
        result = await mcp_server.handle("tools/list", {})

        create_post = next(t for t in result["tools"] if "create_post" in t["name"])
        assert "inputSchema" in create_post
        assert "properties" in create_post["inputSchema"]
        assert "title" in create_post["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_list_tools_empty_when_no_tools(self):
        """List tools should return empty list when no tools"""
        pm = MockPluginManager()
        # Add plugin with no tools
        pm.add_plugin(MockPlugin("empty"))
        server = _MCPServer(pm)

        result = await server.handle("tools/list", {})

        assert result["tools"] == []


class TestToolsCall:
    """Tests for tools/call method"""

    @pytest.mark.asyncio
    async def test_call_tool_invalid_name(self, mcp_server):
        """Call tool with invalid name should return error"""
        result = await mcp_server.handle("tools/call", {"name": "invalid"})

        assert "content" in result
        assert "Invalid tool name" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self, mcp_server):
        """Call non-existent tool should return error"""
        result = await mcp_server.handle("tools/call", {"name": "blog.nonexistent"})

        assert "content" in result
        assert "Tool not found" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_plugin_not_found(self, mcp_server):
        """Call tool from non-existent plugin should return error"""
        result = await mcp_server.handle("tools/call", {"name": "nonexistent.tool"})

        assert "content" in result
        assert "Tool not found" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_with_handler(self):
        """Call tool with handler should execute and return result"""
        pm = MockPluginManager()
        plugin = MockPlugin("test")

        async def my_handler(arg1: str):
            return {"result": f"processed: {arg1}"}

        plugin.add_tool("my_tool", "Test tool", {"type": "object"}, my_handler)
        pm.add_plugin(plugin)
        server = _MCPServer(pm)

        result = await server.handle("tools/call", {
            "name": "test.my_tool",
            "arguments": {"arg1": "hello"}
        })

        assert "content" in result
        assert "processed: hello" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_with_mcp_call(self):
        """Call tool with mcp_call method should use it"""
        pm = MockPluginManager()
        plugin = MockPlugin("test")
        plugin.mcp_call = AsyncMock(return_value={"mcp": "result"})
        plugin.add_tool("my_tool", "Test tool", {"type": "object"})
        pm.add_plugin(plugin)
        server = _MCPServer(pm)

        result = await server.handle("tools/call", {
            "name": "test.my_tool",
            "arguments": {}
        })

        assert "content" in result
        assert "mcp" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_tool_exception_handling(self):
        """Tool exception should be caught and returned as error"""
        pm = MockPluginManager()
        plugin = MockPlugin("test")

        async def failing_handler():
            raise ValueError("Something went wrong")

        plugin.add_tool("fail", "Failing tool", {"type": "object"}, failing_handler)
        pm.add_plugin(plugin)
        server = _MCPServer(pm)

        result = await server.handle("tools/call", {
            "name": "test.fail",
            "arguments": {}
        })

        assert "isError" in result
        assert result["isError"] is True
        assert "Error" in result["content"][0]["text"]


# ============================================================
#  Resources Tests
# ============================================================

class TestResourcesList:
    """Tests for resources/list method"""

    @pytest.mark.asyncio
    async def test_list_resources_returns_all(self, mcp_server):
        """List resources should return all registered resources"""
        result = await mcp_server.handle("resources/list", {})

        assert "resources" in result
        assert len(result["resources"]) == 1  # notes://recent

    @pytest.mark.asyncio
    async def test_list_resources_includes_metadata(self, mcp_server):
        """Resources should include uri, name, mimeType"""
        result = await mcp_server.handle("resources/list", {})

        resource = result["resources"][0]
        assert "uri" in resource
        assert "name" in resource
        assert "mimeType" in resource

    @pytest.mark.asyncio
    async def test_list_resources_empty_when_none(self):
        """List resources should return empty when no resources"""
        pm = MockPluginManager()
        pm.add_plugin(MockPlugin("empty"))
        server = _MCPServer(pm)

        result = await server.handle("resources/list", {})

        assert result["resources"] == []


class TestResourcesRead:
    """Tests for resources/read method"""

    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self, mcp_server):
        """Read resource with invalid URI should return error"""
        result = await mcp_server.handle("resources/read", {"uri": "invalid"})

        assert "contents" in result
        assert "Invalid URI" in result["contents"][0]["text"]

    @pytest.mark.asyncio
    async def test_read_resource_not_found(self, mcp_server):
        """Read non-existent resource should return error"""
        result = await mcp_server.handle("resources/read", {"uri": "nonexistent://data"})

        assert "contents" in result
        assert "Resource not found" in result["contents"][0]["text"]

    @pytest.mark.asyncio
    async def test_read_resource_success(self, mcp_server):
        """Read existing resource should return content"""
        result = await mcp_server.handle("resources/read", {"uri": "notes://recent"})

        assert "contents" in result
        assert len(result["contents"]) == 1
        assert result["contents"][0]["uri"] == "notes://recent"
        assert "mimeType" in result["contents"][0]

    @pytest.mark.asyncio
    async def test_read_resource_exception_handling(self):
        """Resource handler exception should be caught"""
        pm = MockPluginManager()
        plugin = MockPlugin("test")
        plugin.add_resource(
            "test://error",
            "Error Resource",
            "text/plain",
            AsyncMock(side_effect=ValueError("Resource error"))
        )
        pm.add_plugin(plugin)
        server = _MCPServer(pm)

        result = await server.handle("resources/read", {"uri": "test://error"})

        assert "contents" in result
        assert "Error" in result["contents"][0]["text"]


# ============================================================
#  Prompts Tests
# ============================================================

class TestPromptsList:
    """Tests for prompts/list method"""

    @pytest.mark.asyncio
    async def test_list_prompts_returns_all(self, mcp_server):
        """List prompts should return all registered prompts"""
        result = await mcp_server.handle("prompts/list", {})

        assert "prompts" in result
        assert len(result["prompts"]) == 1  # auth.login_help

    @pytest.mark.asyncio
    async def test_list_prompts_namespaced(self, mcp_server):
        """Prompts should be namespaced with plugin name"""
        result = await mcp_server.handle("prompts/list", {})

        assert result["prompts"][0]["name"] == "auth.login_help"

    @pytest.mark.asyncio
    async def test_list_prompts_includes_arguments(self, mcp_server):
        """Prompts should include argument definitions"""
        result = await mcp_server.handle("prompts/list", {})

        prompt = result["prompts"][0]
        assert "arguments" in prompt
        assert len(prompt["arguments"]) == 1
        assert prompt["arguments"][0]["name"] == "username"


class TestPromptsGet:
    """Tests for prompts/get method"""

    @pytest.mark.asyncio
    async def test_get_prompt_invalid_name(self, mcp_server):
        """Get prompt with invalid name should return error"""
        result = await mcp_server.handle("prompts/get", {"name": "invalid"})

        assert result["description"] == "Invalid prompt name"
        assert result["messages"] == []

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self, mcp_server):
        """Get non-existent prompt should return error"""
        result = await mcp_server.handle("prompts/get", {"name": "auth.nonexistent"})

        assert result["description"] == "Prompt not found"
        assert result["messages"] == []

    @pytest.mark.asyncio
    async def test_get_prompt_success(self, mcp_server):
        """Get existing prompt should return template"""
        result = await mcp_server.handle("prompts/get", {"name": "auth.login_help"})

        assert "description" in result
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_prompt_template_substitution(self, mcp_server):
        """Get prompt should substitute template variables"""
        result = await mcp_server.handle("prompts/get", {
            "name": "auth.login_help",
            "arguments": {"username": "alice"}
        })

        text = result["messages"][0]["content"]["text"]
        assert "alice" in text
        assert "{{username}}" not in text

    @pytest.mark.asyncio
    async def test_get_prompt_missing_argument(self, mcp_server):
        """Get prompt with missing argument should keep placeholder"""
        result = await mcp_server.handle("prompts/get", {
            "name": "auth.login_help",
            "arguments": {}
        })

        text = result["messages"][0]["content"]["text"]
        assert "{{username}}" in text


# ============================================================
#  Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Tests for general error handling"""

    @pytest.mark.asyncio
    async def test_unknown_method_raises_error(self, mcp_server):
        """Unknown method should raise ValueError"""
        with pytest.raises(ValueError) as exc_info:
            await mcp_server.handle("unknown/method", {})

        assert "Unknown method" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_params_handled(self, mcp_server):
        """Methods should handle empty params"""
        result = await mcp_server.handle("initialize", {})

        assert "protocolVersion" in result


# ============================================================
#  Integration Tests
# ============================================================

class TestIntegration:
    """Integration tests for full MCP workflow"""

    @pytest.mark.asyncio
    async def test_full_initialize_then_list_tools(self, mcp_server):
        """Full workflow: initialize, then list tools"""
        # Initialize
        init_result = await mcp_server.handle("initialize", {})
        assert init_result["protocolVersion"] == "2024-11-05"

        # List tools
        tools_result = await mcp_server.handle("tools/list", {})
        assert len(tools_result["tools"]) > 0

    @pytest.mark.asyncio
    async def test_multiple_plugins_all_registered(self):
        """Multiple plugins should all have their items registered"""
        pm = MockPluginManager()

        # Add multiple plugins with different MCP items
        p1 = MockPlugin("p1")
        p1.add_tool("t1", "Tool 1", {})
        p1.add_resource("p1://r1", "Resource 1", "text/plain", AsyncMock(return_value="data"))
        pm.add_plugin(p1)

        p2 = MockPlugin("p2")
        p2.add_tool("t2", "Tool 2", {})
        p2.add_prompt("pr2", "Prompt 2", "template")
        pm.add_plugin(p2)

        server = _MCPServer(pm)

        tools = await server.handle("tools/list", {})
        resources = await server.handle("resources/list", {})
        prompts = await server.handle("prompts/list", {})

        assert len(tools["tools"]) == 2
        assert len(resources["resources"]) == 1
        assert len(prompts["prompts"]) == 1
