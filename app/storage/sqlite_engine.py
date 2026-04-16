"""SQLite storage engine implementation"""
import aiosqlite
import json
import hashlib
import time
from typing import Any, Optional, List, Dict
from contextlib import asynccontextmanager

from .interface import Engine, LogEntry, RaftIndex


class SQLiteEngine(Engine):
    """SQLite storage engine - Phase 1 implementation"""
    
    # Core business tables
    SCHEMA = """
    -- Users
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at INTEGER NOT NULL,
        role TEXT DEFAULT 'user',
        avatar TEXT,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );
    
    -- Contents (shared by plugins)
    CREATE TABLE IF NOT EXISTS contents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER,
        plugin_type TEXT NOT NULL,
        author_id INTEGER NOT NULL,
        title TEXT,
        body TEXT,
        meta_json TEXT,
        tags TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        status TEXT DEFAULT 'draft',
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );
    
    -- Files
    CREATE TABLE IF NOT EXISTS objects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER,
        filename TEXT NOT NULL,
        size INTEGER,
        mime_type TEXT,
        storage_path TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0
    );
    
    -- Tasks
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER,
        plugin_type TEXT NOT NULL,
        title TEXT NOT NULL,
        due_at INTEGER,
        status TEXT DEFAULT 'pending',
        meta_json TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0
    );
    
    -- Plugins
    CREATE TABLE IF NOT EXISTS plugins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        version TEXT,
        enabled INTEGER DEFAULT 1,
        config TEXT,
        node_selector TEXT,
        created_at INTEGER NOT NULL
    );
    
    -- Templates
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        display_name TEXT,
        template_version TEXT,
        author TEXT,
        plugin_types TEXT,
        source TEXT DEFAULT 'builtin',
        preview_path TEXT,
        config_schema TEXT,
        files BLOB,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        record_version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );
    
    -- Site template bindings
    CREATE TABLE IF NOT EXISTS site_template_bindings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER,
        plugin_type TEXT NOT NULL,
        template_name TEXT NOT NULL,
        template_config TEXT,
        UNIQUE(site_id, plugin_type)
    );
    
    -- Raft log (reserved for Phase 2+)
    CREATE TABLE IF NOT EXISTS _raft_log (
        term INTEGER NOT NULL,
        idx INTEGER NOT NULL,
        timestamp INTEGER NOT NULL,
        op TEXT NOT NULL,
        table_name TEXT NOT NULL,
        record_id INTEGER,
        data BLOB,
        checksum TEXT,
        PRIMARY KEY (term, idx)
    );
    
    -- Metadata
    CREATE TABLE IF NOT EXISTS _meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    
    -- Full-text search (commented out for now, enable when needed)
    -- CREATE VIRTUAL TABLE IF NOT EXISTS contents_fts USING fts5(
    --     title, body, tags,
    --     content=contents,
    --     content_rowid=id
    -- );
    
    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_contents_plugin ON contents(plugin_type, status);
    CREATE INDEX IF NOT EXISTS idx_contents_author ON contents(author_id);
    CREATE INDEX IF NOT EXISTS idx_contents_created ON contents(created_at);
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._mode = "sqlite"
        self._term = 0
        self._index = 0
    
    async def start(self) -> None:
        """Start the engine"""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        # Enable WAL mode
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA cache_size=-64000")  # 64MB
        
        # Initialize schema
        await self._db.executescript(self.SCHEMA)
        await self._db.commit()
        
        # Load current index
        await self._load_index()
    
    async def _load_index(self) -> None:
        """Load current Raft index from meta"""
        # Load term
        async with self._db.execute(
            "SELECT value FROM _meta WHERE key = 'raft_term'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                self._term = int(row[0])
        
        # Load index - prefer max from log table
        async with self._db.execute(
            "SELECT MAX(idx) FROM _raft_log WHERE term = ?", (self._term,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                self._index = int(row[0])
        
        # Fallback to meta
        if self._index == 0:
            async with self._db.execute(
                "SELECT value FROM _meta WHERE key = 'raft_index'"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    self._index = int(row[0])
    
    async def stop(self) -> None:
        """Stop the engine"""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def get(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        """Read single record"""
        async with self._db.execute(
            f"SELECT * FROM {table} WHERE id = ?", (record_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def put(self, table: str, record_id: int, data: Dict[str, Any]) -> int:
        """Write record with log tracking"""
        now = int(time.time())
        
        # Prepare data
        data['updated_at'] = now
        if record_id == 0:
            data['created_at'] = now
            data.pop('id', None)
            
            # Insert
            columns = list(data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = [data.get(c) for c in columns]
            
            cursor = await self._db.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            record_id = cursor.lastrowid
        else:
            # Update
            data['id'] = record_id
            columns = [k for k in data.keys() if k != 'id']
            set_clause = ', '.join([f"{k} = ?" for k in columns])
            values = [data.get(c) for c in columns] + [record_id]
            
            await self._db.execute(
                f"UPDATE {table} SET {set_clause} WHERE id = ?",
                values
            )
        
        # Log the operation (for migration support)
        self._index += 1
        log_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        checksum = hashlib.sha256(log_data).hexdigest()[:16]
        
        await self._db.execute(
            """INSERT INTO _raft_log (term, idx, timestamp, op, table_name, record_id, data, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (self._term, self._index, now, 'UPDATE', table, record_id, log_data, checksum)
        )
        
        # Update meta
        await self._db.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('raft_index', ?)",
            (str(self._index),)
        )
        
        await self._db.commit()
        return record_id
    
    async def delete(self, table: str, record_id: int) -> None:
        """Delete record"""
        now = int(time.time())
        
        await self._db.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        
        # Log the deletion
        self._index += 1
        await self._db.execute(
            """INSERT INTO _raft_log (term, idx, timestamp, op, table_name, record_id, data, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (self._term, self._index, now, 'DELETE', table, record_id, b'', '')
        )
        
        await self._db.commit()
    
    async def query(self, table: str, **filters) -> List[Dict[str, Any]]:
        """Query records"""
        if filters:
            where_clause = ' AND '.join([f"{k} = ?" for k in filters.keys()])
            params = tuple(filters.values())
            sql = f"SELECT * FROM {table} WHERE {where_clause}"
        else:
            sql = f"SELECT * FROM {table}"
            params = ()
        
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute raw SQL"""
        await self._db.execute(sql, params)
        await self._db.commit()
    
    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch one row"""
        async with self._db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows"""
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    @asynccontextmanager
    async def transaction(self):
        """Transaction context"""
        await self._db.execute("BEGIN")
        try:
            yield
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
    
    async def export(self, since: RaftIndex) -> List[LogEntry]:
        """Export incremental logs for migration"""
        rows = await self.fetchall(
            """SELECT * FROM _raft_log 
               WHERE term > ? OR (term = ? AND idx > ?)
               ORDER BY term, idx""",
            (since.term, since.term, since.index)
        )
        
        return [
            LogEntry(
                index=RaftIndex(term=row['term'], index=row['idx']),
                timestamp=row['timestamp'],
                op=row['op'],
                table=row['table_name'],
                record_id=row['record_id'],
                data=row['data'],
                checksum=row['checksum']
            )
            for row in rows
        ]
    
    async def import_entries(self, entries: List[LogEntry]) -> None:
        """Import logs during migration"""
        async with self.transaction():
            for entry in entries:
                # Replay the operation
                if entry.op in ('INSERT', 'UPDATE'):
                    data = json.loads(entry.data)
                    await self.put(entry.table, entry.record_id, data)
                elif entry.op == 'DELETE':
                    await self.delete(entry.table, entry.record_id)
    
    def current_index(self) -> RaftIndex:
        """Current log position"""
        return RaftIndex(term=self._term, index=self._index)
    
    @property
    def mode(self) -> str:
        return self._mode
