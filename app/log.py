"""
app/log.py — 结构化日志框架
基于 Python 标准库 logging，支持：
  - 控制台彩色输出
  - 文件滚动输出（RotatingFileHandler）
  - SQLite 持久化（写入 app_logs 表，供 /board/logs 浏览）

用法：
    from app.log import get_logger
    log = get_logger(__name__)
    log.info("用户登录", extra={"module": "auth"})
    log.error("数据库错误", exc_info=True, extra={"module": "storage"})
"""
import logging
import logging.handlers
import os
import time
import json
import traceback
import asyncio
from typing import Optional, Any

__all__ = ["get_logger", "setup_logging", "LOG_LEVELS", "LOG_MODULES"]

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LOG_MODULES = ["core", "auth", "blog", "microblog", "notes", "board", "mcp", "storage", "route"]

# 全局 engine 引用（由 app 启动时注入，用于 SQLite handler）
_engine: Optional[Any] = None


# ------------------------------------------------------------------
# 控制台 Handler（彩色）
# ------------------------------------------------------------------

class ColorFormatter(logging.Formatter):
    """ANSI 彩色控制台格式"""
    COLORS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        module = getattr(record, "module_tag", record.name.split(".")[-1])
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{color}[{record.levelname:<8}]{self.RESET} {ts} [{module}] {msg}"


# ------------------------------------------------------------------
# SQLite Handler（异步写入 app_logs 表）
# ------------------------------------------------------------------

class SQLiteHandler(logging.Handler):
    """将日志写入 SQLite app_logs 表（通过 aiosqlite engine）"""

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._queue: list = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_engine(self, engine):
        """注入 SQLiteEngine 实例"""
        global _engine
        _engine = engine

    def emit(self, record: logging.LogRecord):
        if _engine is None:
            return
        try:
            module_tag = getattr(record, "module_tag", record.name.split(".")[-1])
            tb_text = ""
            if record.exc_info:
                tb_text = "".join(traceback.format_exception(*record.exc_info))
            entry = {
                "level": record.levelname,
                "module": module_tag,
                "message": record.getMessage(),
                "context": json.dumps({
                    "name": record.name,
                    "func": record.funcName,
                    "line": record.lineno,
                }, ensure_ascii=False),
                "traceback": tb_text,
                "created_at": int(record.created),
            }
            # 异步写入：尝试获取当前 event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._write(entry))
                else:
                    loop.run_until_complete(self._write(entry))
            except RuntimeError:
                pass  # 无 event loop 时静默跳过
        except Exception:
            self.handleError(record)

    async def _write(self, entry: dict):
        try:
            await _engine.execute(
                "INSERT INTO app_logs (level, module, message, context, traceback, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry["level"], entry["module"], entry["message"],
                 entry["context"], entry["traceback"], entry["created_at"])
            )
        except Exception:
            pass  # 日志写入失败不应影响业务


# ------------------------------------------------------------------
# 全局 Handler 实例（单例）
# ------------------------------------------------------------------

_sqlite_handler = SQLiteHandler(level=logging.INFO)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(ColorFormatter())
_console_handler.setLevel(logging.DEBUG)

_file_handler: Optional[logging.handlers.RotatingFileHandler] = None


def setup_logging(
    data_dir: str = "data",
    log_level: str = "INFO",
    engine=None,
) -> None:
    """
    应用启动时调用一次，配置全局日志。
    :param data_dir: 日志文件目录（data/logs/pywork.log）
    :param log_level: 最低日志级别
    :param engine: SQLiteEngine 实例，用于持久化日志
    """
    global _file_handler

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # 注入 engine
    if engine is not None:
        _sqlite_handler.set_engine(engine)

    # 文件 handler
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "pywork.log")
    _file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    _file_handler.setLevel(numeric_level)
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # 根 logger 配置
    root = logging.getLogger("pywork")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(_console_handler)
    root.addHandler(_file_handler)
    root.addHandler(_sqlite_handler)
    root.propagate = False


def get_logger(name: str, module_tag: Optional[str] = None) -> logging.Logger:
    """
    获取命名 logger。
    :param name: 通常传 __name__
    :param module_tag: 可选，覆盖 module 字段（用于 SQLite 分类）
    """
    # 确保 logger 挂在 pywork 根下
    if not name.startswith("pywork"):
        logger_name = f"pywork.{name}"
    else:
        logger_name = name

    log = logging.getLogger(logger_name)

    # 注入 module_tag 到所有 record
    if module_tag:
        class _TagFilter(logging.Filter):
            def filter(self, record):
                record.module_tag = module_tag
                return True
        log.addFilter(_TagFilter())

    return log
