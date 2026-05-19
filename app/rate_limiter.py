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
        key = self._make_key(identifier)
        now = int(time.time())
        expires_at = now + interval

        # 使用 INSERT OR REPLACE 的原子性：仅当不存在或已过期时才插入
        existing = await self._engine.fetchone(
            "SELECT expires_at FROM rate_limits WHERE key = ? AND expires_at > ?",
            (key, now)
        )

        if existing:
            remaining = existing["expires_at"] - now
            return False, remaining

        await self._engine.execute(
            "INSERT OR REPLACE INTO rate_limits (key, value, expires_at) VALUES (?, ?, ?)",
            (key, str(now), expires_at)
        )
        return True, 0

    async def cleanup(self, max_age: int = 3600) -> int:
        """清理过期记录，返回删除数量"""
        now = int(time.time())
        cursor = await self._engine.execute(
            "DELETE FROM rate_limits WHERE expires_at < ?",
            (now,)
        )
        return cursor.rowcount if cursor else 0


class SlidingWindowRateLimiter:
    """滑动窗口速率限制器（用于 MCP 等需要精确计数的场景）

    使用两个时间桶加权实现真正的滑动窗口：
    - 当前桶：当前时间窗口内的计数
    - 上一个桶：上一个时间窗口内的计数
    - 加权公式：weighted = prev_count * (1 - elapsed/window) + curr_count
    """

    def __init__(self, engine, key_prefix: str = ""):
        self._engine = engine
        self._prefix = key_prefix

    def _make_key(self, identifier: str, window: int, now: int) -> tuple[str, str]:
        """生成当前和上一个时间桶的键"""
        now_bucket = now - (now % window)
        prev_bucket = now_bucket - window
        base = f"{self._prefix}{identifier}" if self._prefix else identifier
        return f"{base}:{now_bucket}", f"{base}:{prev_bucket}"

    async def check_and_record(self, identifier: str, max_requests: int, window: int) -> tuple[bool, int]:
        """
        检查滑动窗口限制并记录（原子操作）。
        返回 (allowed, weighted_count)。
        """
        now = int(time.time())
        curr_key, prev_key = self._make_key(identifier, window, now)
        expires_at = now + window

        # 读取当前桶和上一个桶的计数
        curr_row = await self._engine.fetchone(
            "SELECT value FROM rate_limits WHERE key = ? AND expires_at > ?",
            (curr_key, now)
        )
        prev_row = await self._engine.fetchone(
            "SELECT value FROM rate_limits WHERE key = ? AND expires_at > ?",
            (prev_key, now)
        )

        curr_count = int(curr_row["value"]) if curr_row else 0
        prev_count = int(prev_row["value"]) if prev_row else 0

        # 计算加权计数：上一个桶按剩余时间比例衰减
        bucket_start = now - (now % window)
        elapsed = now - bucket_start
        weight = 1.0 - (elapsed / window)
        weighted_count = int(prev_count * weight) + curr_count

        if weighted_count >= max_requests:
            return False, weighted_count

        # 原子递增当前桶计数
        if curr_row:
            await self._engine.execute(
                "UPDATE rate_limits SET value = ? WHERE key = ?",
                (str(curr_count + 1), curr_key)
            )
        else:
            await self._engine.execute(
                "INSERT OR REPLACE INTO rate_limits (key, value, expires_at) VALUES (?, ?, ?)",
                (curr_key, "1", expires_at)
            )

        return True, weighted_count + 1

    async def cleanup(self, max_age: int = 3600) -> int:
        """清理过期记录，返回删除数量"""
        now = int(time.time())
        cursor = await self._engine.execute(
            "DELETE FROM rate_limits WHERE expires_at < ?",
            (now,)
        )
        return cursor.rowcount if cursor else 0
