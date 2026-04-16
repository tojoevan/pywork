"""Storage layer abstraction"""
from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict
from dataclasses import dataclass
from contextlib import asynccontextmanager


@dataclass
class RaftIndex:
    """Raft log position"""
    term: int
    index: int


@dataclass
class LogEntry:
    """Replication log entry"""
    index: RaftIndex
    timestamp: int
    op: str  # INSERT | UPDATE | DELETE
    table: str
    record_id: int
    data: bytes  # JSON
    checksum: str


class Engine(ABC):
    """Storage engine abstraction"""
    
    @abstractmethod
    async def get(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        """Read single record"""
        pass
    
    @abstractmethod
    async def put(self, table: str, record_id: int, data: Dict[str, Any]) -> None:
        """Write record"""
        pass
    
    @abstractmethod
    async def delete(self, table: str, record_id: int) -> None:
        """Delete record"""
        pass
    
    @abstractmethod
    async def query(self, table: str, **filters) -> List[Dict[str, Any]]:
        """Query records"""
        pass
    
    @abstractmethod
    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute raw SQL"""
        pass
    
    @abstractmethod
    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch one row"""
        pass
    
    @abstractmethod
    async def fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows"""
        pass
    
    @asynccontextmanager
    @abstractmethod
    async def transaction(self):
        """Transaction context"""
        pass
    
    # Migration support (Phase 1 implements, Phase 2+ uses)
    @abstractmethod
    async def export(self, since: RaftIndex) -> List[LogEntry]:
        """Export incremental logs"""
        pass
    
    @abstractmethod
    async def import_entries(self, entries: List[LogEntry]) -> None:
        """Import logs"""
        pass
    
    @abstractmethod
    def current_index(self) -> RaftIndex:
        """Current log position"""
        pass
    
    # Lifecycle
    @abstractmethod
    async def start(self) -> None:
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        pass
    
    @property
    @abstractmethod
    def mode(self) -> str:
        """Engine mode: sqlite | master | replica | raft"""
        pass
