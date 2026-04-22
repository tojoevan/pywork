"""
app/config.py — Pydantic 配置验证层

职责：
  1. AppConfig: pydantic 模型，定义所有系统配置字段 + 校验规则
  2. SiteConfigManager: site_config 表读写封装，支持运行时热更新
  3. 自动迁移: 从 site_config 表 + 环境变量 + 默认值合并，启动时自动同步

升级安全：
  - 不修改 site_config 表结构（保持 key-value 格式）
  - 启动时从表读取 → 合并 env → 写回缺失的默认值
  - 现有数据零影响，新增字段自动填充默认值
"""
import os
import json
import time
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, field_validator


# ============================================================
#  Pydantic 配置模型
# ============================================================

class AppConfig(BaseModel):
    """
    系统配置模型。

    数据来源优先级：环境变量 > site_config 表 > 默认值
    """
    # --- 基础信息 ---
    title: str = "pyWork"
    description: str = "多用户数字工作台"
    logo_text: str = "pyWork"
    footer_text: str = "© 2026 pyWork. All rights reserved."
    announcement: str = ""

    # --- 外观 ---
    primary_color: str = "#3498db"

    # --- 运行时 ---
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    # --- 数据库 ---
    db_path: str = "./data/pywork.db"

    # --- 插件 ---
    enabled_plugins: List[str] = Field(
        default=["blog", "auth", "microblog", "about", "notes", "board"]
    )

    # --- GitHub OAuth ---
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    github_redirect_uri: str = "http://localhost:8080/auth/github/callback"

    # --- 上传 ---
    upload_dir: str = "./data/uploads"
    max_upload_size: int = 10 * 1024 * 1024  # 10 MB

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"port must be 1-65535, got {v}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(f"invalid log_level: {v}")
        return v


# ============================================================
#  site_config 表字段注册表
# ============================================================

# 标记哪些 AppConfig 字段应该持久化到 site_config 表
# key: AppConfig 字段名, value: site_config 表中的 key
SITE_CONFIG_KEYS = {
    "title": "title",
    "description": "description",
    "logo_text": "logo_text",
    "footer_text": "footer_text",
    "primary_color": "primary_color",
    "announcement": "announcement",
}


# ============================================================
#  SiteConfigManager — site_config 表读写封装
# ============================================================

class SiteConfigManager:
    """
    管理 site_config 表的读写。

    特性：
    - 读写走统一入口，避免各插件各自拼 SQL
    - 缓存机制，减少数据库查询
    - 更新时自动清除 TemplateEngine 的 _site_cache
    """

    def __init__(self, engine=None):
        self._engine = engine
        self._cache: Optional[Dict[str, str]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 30  # 30 秒缓存

    def set_engine(self, engine):
        """注入 Engine 实例（延迟初始化）"""
        self._engine = engine

    async def ensure_table(self):
        """确保 site_config 表存在"""
        if self._engine is None:
            return
        await self._engine.execute("""
            CREATE TABLE IF NOT EXISTS site_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

    async def load(self) -> Dict[str, str]:
        """从数据库加载所有 site_config，带缓存"""
        if self._cache is not None and (time.time() - self._cache_time) < self._cache_ttl:
            return self._cache

        try:
            rows = await self._engine.fetchall("SELECT key, value FROM site_config")
            self._cache = {row["key"]: row["value"] for row in rows} if rows else {}
        except Exception:
            self._cache = {}
        self._cache_time = time.time()
        return self._cache

    async def get(self, key: str, default: str = "") -> str:
        """获取单个配置值"""
        settings = await self.load()
        return settings.get(key, default)

    async def set(self, key: str, value: str):
        """设置单个配置值（UPSERT）"""
        if self._engine is None:
            return
        await self.ensure_table()
        await self._engine.execute(
            "INSERT OR REPLACE INTO site_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        # 清除缓存
        self._cache = None

    async def batch_set(self, data: Dict[str, str], allowed_keys: Optional[List[str]] = None):
        """批量设置配置值"""
        if self._engine is None:
            return
        await self.ensure_table()
        for key, value in data.items():
            if allowed_keys is None or key in allowed_keys:
                await self._engine.execute(
                    "INSERT OR REPLACE INTO site_config (key, value) VALUES (?, ?)",
                    (key, value),
                )
        # 清除缓存
        self._cache = None

    async def get_all(self) -> Dict[str, str]:
        """获取所有配置（返回副本）"""
        settings = await self.load()
        return dict(settings)

    def invalidate_cache(self):
        """清除缓存"""
        self._cache = None


# ============================================================
#  自动迁移：启动时合并配置
# ============================================================

async def build_config(engine=None) -> AppConfig:
    """
    从多个来源构建 AppConfig 实例。

    优先级（高→低）：环境变量 > site_config 表 > 默认值

    自动迁移逻辑：
    1. 从 site_config 表读取现有值
    2. 用环境变量覆盖（PYWORK_ 前缀，如 PYWORK_TITLE）
    3. 用 pydantic 默认值填充缺失字段
    4. 将 site_config 表中缺失的字段（新版本新增）写回数据库

    :param engine: SQLiteEngine 实例（可选，为 None 时跳过数据库读写）
    :return: AppConfig 实例
    """
    # 第一步：从 site_config 表加载
    db_values: Dict[str, str] = {}
    if engine is not None:
        try:
            rows = await engine.fetchall("SELECT key, value FROM site_config")
            for row in rows:
                db_values[row["key"]] = row["value"]
        except Exception:
            pass  # 表可能不存在（首次启动）

    # 第二步：环境变量覆盖（PYWORK_ 前缀）
    env_overrides = {
        "title": os.getenv("PYWORK_TITLE"),
        "description": os.getenv("PYWORK_DESCRIPTION"),
        "logo_text": os.getenv("PYWORK_LOGO_TEXT"),
        "footer_text": os.getenv("PYWORK_FOOTER_TEXT"),
        "primary_color": os.getenv("PYWORK_PRIMARY_COLOR"),
        "announcement": os.getenv("PYWORK_ANNOUNCEMENT"),
        "debug": os.getenv("PYWORK_DEBUG"),
        "host": os.getenv("PYWORK_HOST"),
        "port": os.getenv("PYWORK_PORT"),
        "log_level": os.getenv("PYWORK_LOG_LEVEL", os.getenv("LOG_LEVEL")),
        "db_path": os.getenv("PYWORK_DB_PATH"),
        "upload_dir": os.getenv("PYWORK_UPLOAD_DIR"),
        "max_upload_size": os.getenv("PYWORK_MAX_UPLOAD_SIZE"),
        "github_client_id": os.getenv("GITHUB_CLIENT_ID"),
        "github_client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
        "github_redirect_uri": os.getenv("GITHUB_REDIRECT_URI"),
        "enabled_plugins": os.getenv("PYWORK_ENABLED_PLUGINS"),
    }
    # 移除 None 值
    env_overrides = {k: v for k, v in env_overrides.items() if v is not None}

    # 第三步：合并构建字段字典
    fields: Dict[str, Any] = {}

    # 先填 site_config 表中的值（通过 SITE_CONFIG_KEYS 映射）
    for model_field, db_key in SITE_CONFIG_KEYS.items():
        if db_key in db_values:
            fields[model_field] = db_values[db_key]

    # 环境变量覆盖
    for key, value in env_overrides.items():
        if key == "debug":
            fields["debug"] = value.lower() in ("1", "true", "yes")
        elif key == "port":
            fields["port"] = int(value)
        elif key == "max_upload_size":
            fields["max_upload_size"] = int(value)
        elif key == "enabled_plugins":
            fields["enabled_plugins"] = [p.strip() for p in value.split(",") if p.strip()]
        else:
            fields[key] = value

    # 用 pydantic 模型验证 + 填默认值
    config = AppConfig(**fields)

    # 第四步：自动迁移 — 将新字段写回 site_config 表
    if engine is not None:
        try:
            # 确保 site_config 表存在
            await engine.execute("""
                CREATE TABLE IF NOT EXISTS site_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # 对比并写入缺失的默认值
            for model_field, db_key in SITE_CONFIG_KEYS.items():
                if db_key not in db_values:
                    # 新字段：写入默认值到数据库
                    default_val = getattr(config, model_field, "")
                    if default_val:
                        await engine.execute(
                            "INSERT OR IGNORE INTO site_config (key, value) VALUES (?, ?)",
                            (db_key, default_val),
                        )
        except Exception:
            pass  # 迁移失败不应阻止启动

    return config


def config_to_dict(config: AppConfig) -> Dict[str, Any]:
    """
    将 AppConfig 转为普通 dict（用于模板注入等场景）。

    保留向后兼容：模板中通过 Site.title 访问
    """
    return config.model_dump()


# ============================================================
#  向后兼容包装器
# ============================================================

class ConfigWrapper:
    """
    让 AppConfig 实例同时支持属性访问和 dict 风格访问。

    用法：
        config = ConfigWrapper(app_config_instance)

        # 属性访问（推荐）
        config.title
        config.port

        # dict 风格访问（向后兼容）
        config.get("title", "默认值")
        config["title"]

        # 迭代
        for key, value in config.items(): ...
    """

    def __init__(self, config: AppConfig):
        self._config = config

    def __getattr__(self, name: str):
        try:
            return getattr(self._config, name)
        except AttributeError:
            raise AttributeError(f"Config has no field '{name}'")

    def __getitem__(self, key: str):
        try:
            return getattr(self._config, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self._config, key)
        except AttributeError:
            return default

    def __contains__(self, key: str) -> bool:
        return hasattr(self._config, key)

    def __repr__(self) -> str:
        return f"ConfigWrapper({self._config!r})"

    def items(self):
        return self._config.model_dump().items()

    def keys(self):
        return self._config.model_dump().keys()

    def values(self):
        return self._config.model_dump().values()
