"""LLM Config plugin - manage LLM API configurations and provide LLM call capability"""
from typing import List, Dict, Any, Optional
import time
import aiohttp

from app.plugin import Plugin, PluginContext, MCPTool, Route
from starlette.responses import HTMLResponse


class LlmConfigPlugin(Plugin):
    """LLM Config plugin - manage LLM API connections"""

    @property
    def name(self) -> str:
        return "llm_config"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def init(self, ctx: PluginContext) -> None:
        self.engine = ctx.engine
        self.config = ctx.config
        self.ctx = ctx
        self._ctx = ctx
        await self._ensure_tables()

    async def _ensure_tables(self) -> None:
        """Create llm_configs table if not exists"""
        await self.engine.execute("""
        CREATE TABLE IF NOT EXISTS llm_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT 'gpt-4o',
            temperature REAL DEFAULT 0.7,
            max_tokens INTEGER DEFAULT 4096,
            is_default INTEGER DEFAULT 0,
            system_prompt TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        await self.engine.execute("""
        CREATE INDEX IF NOT EXISTS idx_llm_configs_name ON llm_configs(name)
        """)

    def routes(self) -> List[Route]:
        return [
            Route("/llm-config", "GET", self.config_page, "llm_config.page"),
            Route("/api/llm-configs", "GET", self.list_configs_api, "llm_config.list_api"),
            Route("/api/llm-configs", "POST", self.create_config_api, "llm_config.create_api"),
            Route("/api/llm-configs/{config_id}", "PUT", self.update_config_api, "llm_config.update_api"),
            Route("/api/llm-configs/{config_id}", "DELETE", self.delete_config_api, "llm_config.delete_api"),
            Route("/api/llm-configs/{config_id}/test", "POST", self.test_config_api, "llm_config.test_api"),
            Route("/api/llm-configs/{config_id}/default", "POST", self.set_default_api, "llm_config.set_default_api"),
        ]

    def mcp_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="list_llm_configs",
                description="List all LLM API configurations (api_key is masked)",
                input_schema={
                    "type": "object",
                    "properties": {}
                },
                handler=self.list_configs
            ),
            MCPTool(
                name="create_llm_config",
                description="Create a new LLM API configuration",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Configuration name"},
                        "base_url": {"type": "string", "description": "API base URL (e.g. https://api.openai.com/v1)"},
                        "api_key": {"type": "string", "description": "API key"},
                        "model": {"type": "string", "description": "Model name", "default": "gpt-4o"},
                        "temperature": {"type": "number", "description": "Temperature (0-2)", "default": 0.7},
                        "max_tokens": {"type": "integer", "description": "Max tokens", "default": 4096},
                        "system_prompt": {"type": "string", "description": "System prompt", "default": ""},
                        "is_default": {"type": "boolean", "description": "Set as default config", "default": False}
                    },
                    "required": ["name", "base_url", "api_key"]
                },
                handler=self.create_config
            ),
            MCPTool(
                name="update_llm_config",
                description="Update an existing LLM API configuration",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Configuration ID"},
                        "name": {"type": "string"},
                        "base_url": {"type": "string"},
                        "api_key": {"type": "string"},
                        "model": {"type": "string"},
                        "temperature": {"type": "number"},
                        "max_tokens": {"type": "integer"},
                        "system_prompt": {"type": "string"},
                        "is_default": {"type": "boolean"}
                    },
                    "required": ["id"]
                },
                handler=self.update_config
            ),
            MCPTool(
                name="delete_llm_config",
                description="Delete an LLM API configuration",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Configuration ID"}
                    },
                    "required": ["id"]
                },
                handler=self.delete_config
            ),
            MCPTool(
                name="test_llm_config",
                description="Test an LLM API configuration by sending a simple request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "Configuration ID to test"}
                    },
                    "required": ["id"]
                },
                handler=self.test_config
            ),
            MCPTool(
                name="call_llm",
                description="Call LLM with a prompt using a configured LLM API. If config_id is not provided, uses the default config.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "User prompt to send to LLM"},
                        "config_id": {"type": "integer", "description": "LLM config ID (optional, uses default if not provided)"},
                        "system_prompt": {"type": "string", "description": "Override system prompt (optional)"},
                        "temperature": {"type": "number", "description": "Override temperature (optional)"},
                        "max_tokens": {"type": "integer", "description": "Override max tokens (optional)"}
                    },
                    "required": ["prompt"]
                },
                handler=self.call_llm
            ),
        ]

    # ========================================================
    #  Core methods
    # ========================================================

    def _mask_api_key(self, api_key: str) -> str:
        """Mask API key for display: sk-****xxxx"""
        if not api_key or len(api_key) < 8:
            return "****"
        return api_key[:4] + "****" + api_key[-4:]

    async def list_configs(self, **kwargs) -> List[Dict[str, Any]]:
        """List all LLM configs (with masked api_key)"""
        rows = await self.engine.fetchall(
            "SELECT * FROM llm_configs ORDER BY is_default DESC, created_at DESC"
        )
        configs = []
        for row in rows:
            row["api_key_masked"] = self._mask_api_key(row.get("api_key", ""))
            row.pop("api_key", None)
            configs.append(row)
        return configs

    async def get_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Get a single config (with real api_key for internal use)"""
        return await self.engine.fetchone(
            "SELECT * FROM llm_configs WHERE id = ?", (config_id,)
        )

    async def get_default_config(self) -> Optional[Dict[str, Any]]:
        """Get the default config"""
        return await self.engine.fetchone(
            "SELECT * FROM llm_configs WHERE is_default = 1 LIMIT 1"
        )

    async def create_config(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str = "",
        is_default: bool = False,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new LLM config"""
        # MCP auth check
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if not user:
                return {"error": "无效的 MCP Token"}
            if user.get("role") != "admin":
                return {"error": "仅管理员可配置 LLM"}

        now = int(time.time())

        # If setting as default, clear other defaults
        if is_default:
            await self.engine.execute("UPDATE llm_configs SET is_default = 0")

        data = {
            "name": name,
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system_prompt": system_prompt,
            "is_default": 1 if is_default else 0,
            "created_at": now,
            "updated_at": now,
        }

        record_id = await self.engine.put("llm_configs", 0, data)
        return {
            "id": record_id,
            "name": name,
            "model": model,
            "is_default": is_default,
            "created_at": now
        }

    async def update_config(
        self,
        id: int,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update an LLM config"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if not user:
                return {"error": "无效的 MCP Token"}
            if user.get("role") != "admin":
                return {"error": "仅管理员可修改 LLM 配置"}

        existing = await self.engine.fetchone(
            "SELECT * FROM llm_configs WHERE id = ?", (id,)
        )
        if not existing:
            return {"error": "配置不存在"}

        # Update fields
        for key in ["name", "base_url", "model", "system_prompt"]:
            if key in kwargs and kwargs[key] is not None:
                existing[key] = kwargs[key]

        if "base_url" in kwargs and kwargs["base_url"]:
            existing["base_url"] = kwargs["base_url"].rstrip("/")

        if "api_key" in kwargs and kwargs["api_key"]:
            existing["api_key"] = kwargs["api_key"]

        for key in ["temperature", "max_tokens"]:
            if key in kwargs and kwargs[key] is not None:
                existing[key] = kwargs[key]

        if "is_default" in kwargs and kwargs["is_default"] is not None:
            is_default = kwargs["is_default"]
            if is_default:
                await self.engine.execute("UPDATE llm_configs SET is_default = 0")
            existing["is_default"] = 1 if is_default else 0

        existing["updated_at"] = int(time.time())
        await self.engine.put("llm_configs", id, existing)

        return {"id": id, "updated": True}

    async def delete_config(
        self,
        id: int,
        mcp_token: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Delete an LLM config"""
        if mcp_token:
            user = await self.get_current_user_mcp(mcp_token)
            if not user:
                return {"error": "无效的 MCP Token"}
            if user.get("role") != "admin":
                return {"error": "仅管理员可删除 LLM 配置"}

        existing = await self.engine.fetchone(
            "SELECT * FROM llm_configs WHERE id = ?", (id,)
        )
        if not existing:
            return {"error": "配置不存在"}

        await self.engine.execute("DELETE FROM llm_configs WHERE id = ?", (id,))
        return {"id": id, "deleted": True}

    async def test_config(self, id: int, **kwargs) -> Dict[str, Any]:
        """Test an LLM config by sending a simple request"""
        cfg = await self.get_config(id)
        if not cfg:
            return {"error": "配置不存在"}

        try:
            result = await self._do_llm_request(
                config=cfg,
                prompt="Hello, please respond with 'OK' to confirm the connection is working.",
                max_tokens=50
            )
            return {
                "success": True,
                "response": result[:200],
                "model": cfg["model"],
                "base_url": cfg["base_url"]
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": cfg["model"],
                "base_url": cfg["base_url"]
            }

    async def call_llm(
        self,
        prompt: str,
        config_id: int = None,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Call LLM with a prompt. Used by other plugins (e.g., topic summarize)."""
        # Resolve config
        cfg = None
        if config_id:
            cfg = await self.get_config(config_id)
        if not cfg:
            cfg = await self.get_default_config()
        if not cfg:
            return {"error": "未找到 LLM 配置，请先创建配置"}

        try:
            result = await self._do_llm_request(
                config=cfg,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return {
                "content": result,
                "model": cfg["model"],
                "config_id": cfg["id"],
                "config_name": cfg["name"]
            }
        except Exception as e:
            return {"error": f"LLM 调用失败: {str(e)}"}

    async def _do_llm_request(
        self,
        config: Dict,
        prompt: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """Execute an LLM API call using OpenAI Chat Completions compatible protocol"""
        base_url = config["base_url"].rstrip("/")
        url = f"{base_url}/chat/completions"

        # Build messages
        messages = []
        sp = system_prompt or config.get("system_prompt", "")
        if sp:
            messages.append({"role": "system", "content": sp})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": temperature if temperature is not None else config.get("temperature", 0.7),
            "max_tokens": max_tokens if max_tokens is not None else config.get("max_tokens", 4096),
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"LLM API returned {resp.status}: {text[:500]}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    # ========================================================
    #  MCP call dispatcher
    # ========================================================

    async def mcp_call(self, tool_name: str, arguments: Dict, mcp_token: str = None) -> Any:
        """MCP call dispatcher"""
        if tool_name == "list_llm_configs":
            return await self.list_configs()
        elif tool_name == "create_llm_config":
            return await self.create_config(mcp_token=mcp_token, **arguments)
        elif tool_name == "update_llm_config":
            return await self.update_config(mcp_token=mcp_token, **arguments)
        elif tool_name == "delete_llm_config":
            return await self.delete_config(mcp_token=mcp_token, **arguments)
        elif tool_name == "test_llm_config":
            return await self.test_config(**arguments)
        elif tool_name == "call_llm":
            return await self.call_llm(**arguments)
        raise ValueError(f"Unknown tool: {tool_name}")

    # ========================================================
    #  HTTP handlers
    # ========================================================

    async def config_page(self, request, **kwargs):
        """LLM config management page (admin only)"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        configs = await self.engine.fetchall(
            "SELECT id, name, base_url, model, temperature, max_tokens, is_default, system_prompt, created_at, updated_at FROM llm_configs ORDER BY is_default DESC, created_at DESC"
        )
        # Add masked api_key info
        for cfg in configs:
            full = await self.get_config(cfg["id"])
            cfg["api_key_masked"] = self._mask_api_key(full["api_key"]) if full else "****"

        current_user = await self.get_current_user(request)
        html = await self.ctx.template_engine.render("llm_config.html", {
            "nav_page": "llm_config",
            "configs": configs,
            "current_user": current_user,
        })
        return HTMLResponse(content=html)

    async def list_configs_api(self, request, **kwargs):
        """List configs API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect
        configs = await self.list_configs()
        from starlette.responses import JSONResponse
        return JSONResponse({"configs": configs})

    async def create_config_api(self, request, **kwargs):
        """Create config API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        name = (body.get("name") or "").strip()
        base_url = (body.get("base_url") or "").strip()
        api_key = (body.get("api_key") or "").strip()

        if not name or not base_url or not api_key:
            return self.error_json("名称、Base URL 和 API Key 不能为空")

        return await self.create_config(
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=body.get("model", "gpt-4o"),
            temperature=float(body.get("temperature", 0.7)),
            max_tokens=int(body.get("max_tokens", 4096)),
            system_prompt=body.get("system_prompt", ""),
            is_default=body.get("is_default") in (True, "true", "1", 1)
        )

    async def update_config_api(self, request, **kwargs):
        """Update config API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        config_id = int(kwargs.get("config_id", 0))
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form()
            body = dict(form)

        update_data = {"id": config_id}
        for key in ["name", "base_url", "api_key", "model", "system_prompt"]:
            if key in body and body[key]:
                update_data[key] = body[key]
        for key in ["temperature", "max_tokens"]:
            if key in body:
                try:
                    update_data[key] = float(body[key]) if key == "temperature" else int(body[key])
                except (ValueError, TypeError):
                    pass
        if "is_default" in body:
            update_data["is_default"] = body["is_default"] in (True, "true", "1", 1)

        return await self.update_config(**update_data)

    async def delete_config_api(self, request, **kwargs):
        """Delete config API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        config_id = int(kwargs.get("config_id", 0))
        return await self.delete_config(id=config_id)

    async def test_config_api(self, request, **kwargs):
        """Test config API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        config_id = int(kwargs.get("config_id", 0))
        result = await self.test_config(config_id)
        from starlette.responses import JSONResponse
        return JSONResponse(result)

    async def set_default_api(self, request, **kwargs):
        """Set default config API"""
        redirect = await self.require_admin_or_redirect(request)
        if redirect:
            return redirect

        config_id = int(kwargs.get("config_id", 0))
        result = await self.update_config(id=config_id, is_default=True)
        from starlette.responses import JSONResponse
        return JSONResponse(result)
