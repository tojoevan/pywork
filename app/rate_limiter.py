"""基于 SQLite 的速率限制器"""

import time
from typing import Optional


class RateLimiter:
    """SQLite-based rate limiter with automatic cleanup"""

    def __init__(self, engine, key_prefix: str = ""):
        self._engine = engine
        self._prefix = key_prefix

    def _make_key(self, identifier: str) -> str:
        return f"{self._prefix}{identifier}" if self._prefix else identifier

    async def check(self, identifier: str, interval: int) -> tuple[bool, int]:
        """
        检查是否允许请求。
        返回 (allowed, remaining_seconds)。
        """
        key = self._make_key(identifier)
        now = int(time.time())

        row = await self._engine.fetchone(
            "SELECT value, expires_at FROM rate_limits WHERE key = ?",
            (key,)
        )

        if row and row["expires_at"] > now:
            remaining = row["expires_at"] - now
            return False, remaining

        return True, 0

    async def record(self, identifier: str, interval: int) -> None:
        """记录一次请求，设置过期时间"""
        key = self._make_key(identifier)
        now = int(time.time())
        expires_at = now + interval

        await self._engine.execute(
            "INSERT OR REPLACE INTO rate_limits (key, value, expires_at) VALUES (?, ?, ?)",
            (key, str(now), expires_at)
        )

    async def check_and_record(self, identifier: str, interval: int) -> tuple[bool, int]:
        """检查并记录（原子操作）"""
        allowed, remaining = await self.check(identifier, interval)
        if allowed:
            await self.record(identifier, interval)
        return allowed, remaining

    async def cleanup(self, max_age: int = 3600) -> int:
        """清理过期记录，返回删除数量"""
        now = int(time.time())
        cursor = await self._engine.execute(
            "DELETE FROM rate_limits WHERE expires_at < ?",
            (now - max_age,)
        )
        return cursor.rowcount if cursor else 0


class SlidingWindowRateLimiter:
    """滑动窗口速率限制器（用于 MCP 等需要精确计数的场景）"""

    def __init__(self, engine, key_prefix: str = ""):
        self._engine = engine
        self._prefix = key_prefix

    def _make_key(self, identifier: str, window: int) -> str:
        """生成窗口键"""
        now = int(time.time())
        window_start = now - (now % window)
        base = f"{self._prefix}{identifier}" if self._prefix else identifier
        return f"{base}:{window_start}"

    async def check_and_record(self, identifier: str, max_requests: int, window: int) -> tuple[bool, int]:
        """
        检查滑动窗口限制并记录。
        返回 (allowed, current_count)。
        """
        key = self._make_key(identifier, window)
        now = int(time.time())
        expires_at = now + window

        row = await self._engine.fetchone(
            "SELECT value, expires_at FROM rate_limits WHERE key = ?",
            (key,)
        )

        if row and row["expires_at"] > now:
            count = int(row["value"])
            if count >= max_requests:
                return False, count
            count += 1
            await self._engine.execute(
                "UPDATE rate_limits SET value = ? WHERE key = ?",
                (str(count), key)
            )
            return True, count
        else:
            await self._engine.execute(
                "INSERT OR REPLACE INTO rate_limits (key, value, expires_at) VALUES (?, ?, ?)",
                (key, "1", expires_at)
            )
            return True, 1
