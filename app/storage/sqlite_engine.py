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
    
    # Table name whitelist — all SQL-accepting methods validate against this
    ALLOWED_TABLES = frozenset({
        'users', 'blog_posts', 'microblog_posts', 'notes', 'guestbook_entries',
        'objects', 'tasks', 'plugins', 'templates',
        'site_config', 'site_template_bindings', 'sessions', 'cron_jobs',
        'cron_stats', 'board_tasks', 'active_authors', 'mcp_tokens',
        '_meta', '_raft_log', 'app_logs',
    })
    
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
    
    -- Blog posts
    CREATE TABLE IF NOT EXISTS blog_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        tags TEXT DEFAULT '[]',
        visibility TEXT DEFAULT 'private',
        status TEXT DEFAULT 'draft',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );

    -- Microblog posts
    CREATE TABLE IF NOT EXISTS microblog_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        visibility TEXT DEFAULT 'public',
        status TEXT DEFAULT 'public',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );

    -- Notes
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        tags TEXT,
        visibility TEXT DEFAULT 'private',
        status TEXT DEFAULT 'published',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        raft_term INTEGER DEFAULT 0,
        raft_index INTEGER DEFAULT 0,
        version INTEGER DEFAULT 1,
        node_id TEXT DEFAULT 'local'
    );

    -- Guestbook entries
    CREATE TABLE IF NOT EXISTS guestbook_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id INTEGER DEFAULT 0,
        nickname TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        email TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
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
    
    -- MCP Tokens (persistent, replaces in-memory dict)
    CREATE TABLE IF NOT EXISTS mcp_tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        name TEXT DEFAULT 'MCP Client',
        created_at INTEGER NOT NULL,
        last_used INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
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
    
    -- Full-text search index for blog_posts
    CREATE VIRTUAL TABLE IF NOT EXISTS blog_posts_fts USING fts5(
        title, body, tags,
        content='blog_posts',
        content_rowid='id'
    );
    
    -- Triggers to keep FTS in sync with blog_posts
    CREATE TRIGGER IF NOT EXISTS blog_posts_fts_insert AFTER INSERT ON blog_posts BEGIN
        INSERT INTO blog_posts_fts(rowid, title, body, tags)
            VALUES (new.id, new.title, new.body, new.tags);
    END;
    
    CREATE TRIGGER IF NOT EXISTS blog_posts_fts_update AFTER UPDATE ON blog_posts BEGIN
        INSERT INTO blog_posts_fts(blog_posts_fts, rowid, title, body, tags)
            VALUES ('delete', old.id, old.title, old.body, old.tags);
        INSERT INTO blog_posts_fts(rowid, title, body, tags)
            VALUES (new.id, new.title, new.body, new.tags);
    END;
    
    CREATE TRIGGER IF NOT EXISTS blog_posts_fts_delete AFTER DELETE ON blog_posts BEGIN
        INSERT INTO blog_posts_fts(blog_posts_fts, rowid, title, body, tags)
            VALUES ('delete', old.id, old.title, old.body, old.tags);
    END;
    
    -- Indexes for blog_posts
    CREATE INDEX IF NOT EXISTS idx_blog_posts_author ON blog_posts(author_id);
    CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
    CREATE INDEX IF NOT EXISTS idx_blog_posts_created ON blog_posts(created_at);
    
    -- Indexes for microblog_posts
    CREATE INDEX IF NOT EXISTS idx_microblog_posts_author ON microblog_posts(author_id);
    CREATE INDEX IF NOT EXISTS idx_microblog_posts_status ON microblog_posts(status);
    CREATE INDEX IF NOT EXISTS idx_microblog_posts_created ON microblog_posts(created_at);
    
    -- Indexes for notes
    CREATE INDEX IF NOT EXISTS idx_notes_author ON notes(author_id);
    CREATE INDEX IF NOT EXISTS idx_notes_visibility ON notes(visibility);
    CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at);
    
    -- Indexes for guestbook_entries
    CREATE INDEX IF NOT EXISTS idx_guestbook_status ON guestbook_entries(status);
    CREATE INDEX IF NOT EXISTS idx_guestbook_created ON guestbook_entries(created_at);

    -- Application logs
    CREATE TABLE IF NOT EXISTS app_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL DEFAULT 'INFO',
        module TEXT NOT NULL DEFAULT 'core',
        message TEXT NOT NULL,
        context TEXT DEFAULT '',
        traceback TEXT DEFAULT '',
        created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_app_logs_level ON app_logs(level);
    CREATE INDEX IF NOT EXISTS idx_app_logs_module ON app_logs(module);
    CREATE INDEX IF NOT EXISTS idx_app_logs_created ON app_logs(created_at);
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
        
        # Run migrations for existing databases
        await self._run_migrations()
        
        # Compact raft log (keep last 1000 entries)
        deleted = await self.compact_log(keep_last=1000)
        if deleted > 0:
            print(f"✓ Raft log compacted: removed {deleted} old entries")
        
        # Load current index
        await self._load_index()
    
    async def _run_migrations(self) -> None:
        """Run schema migrations for existing databases.
        
        Uses pragma_table_info to detect missing columns and ALTER TABLE to add them.
        Safe to run on every startup — only adds columns that don't exist yet.
        """
        # Migration 001: add visibility column to contents (legacy, kept for old DBs)
        try:
            async with self._db.execute(
                "SELECT name FROM pragma_table_info('contents') WHERE name = 'visibility'"
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await self._db.execute(
                        "ALTER TABLE contents ADD COLUMN visibility TEXT DEFAULT 'private'"
                    )
                    await self._db.commit()
                    print("✓ Migration 001: added visibility column to contents")
        except Exception as e:
            print(f"⚠ Migration 001 skipped: {e}")

        # Migration 002: split contents table into dedicated tables
        await self._migrate_contents_split()

        # Migration 003: add author_id to guestbook_entries
        try:
            async with self._db.execute(
                "SELECT name FROM pragma_table_info('guestbook_entries') WHERE name = 'author_id'"
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await self._db.execute(
                        "ALTER TABLE guestbook_entries ADD COLUMN author_id INTEGER DEFAULT 0"
                    )
                    await self._db.commit()
                    print("✓ Migration 003: added author_id column to guestbook_entries")
        except Exception as e:
            print(f"⚠ Migration 003 skipped: {e}")

        # Migration 004: create FTS5 index for blog_posts
        await self._migrate_fts5()
    
    async def _migrate_contents_split(self) -> None:
        """Migration 002: split contents table into blog_posts, microblog_posts, notes, guestbook_entries.
        
        Idempotent — checks a flag in _meta before running.
        """
        # Check if already migrated
        async with self._db.execute(
            "SELECT value FROM _meta WHERE key = 'migration_002_contents_split'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return  # Already done
        
        # Check if legacy contents table exists
        async with self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contents'"
        ) as cursor:
            if not await cursor.fetchone():
                # No legacy table, nothing to migrate
                await self._db.execute(
                    "INSERT OR REPLACE INTO _meta (key, value) VALUES ('migration_002_contents_split', '1')"
                )
                await self._db.commit()
                return
        
        print("→ Migrating contents table to dedicated tables...")
        
        try:
            # Migrate blog posts
            await self._db.execute("""
                INSERT OR IGNORE INTO blog_posts (id, author_id, title, body, tags, visibility, status, created_at, updated_at, raft_term, raft_index, version, node_id)
                SELECT id, author_id, COALESCE(title, ''), COALESCE(body, ''), COALESCE(tags, '[]'),
                       COALESCE(visibility, 'private'), COALESCE(status, 'draft'),
                       created_at, updated_at, 0, 0, 1, 'local'
                FROM contents WHERE plugin_type = 'blog'
            """)
            
            # Migrate microblog posts (title is empty, body → content)
            await self._db.execute("""
                INSERT OR IGNORE INTO microblog_posts (id, author_id, content, visibility, status, created_at, updated_at, raft_term, raft_index, version, node_id)
                SELECT id, author_id, COALESCE(body, ''), COALESCE(visibility, 'public'), COALESCE(status, 'public'),
                       created_at, updated_at, 0, 0, 1, 'local'
                FROM contents WHERE plugin_type = 'microblog'
            """)
            
            # Migrate notes
            await self._db.execute("""
                INSERT OR IGNORE INTO notes (id, author_id, title, body, tags, visibility, status, created_at, updated_at, raft_term, raft_index, version, node_id)
                SELECT id, author_id, COALESCE(title, ''), COALESCE(body, ''), tags,
                       COALESCE(visibility, 'private'), COALESCE(status, 'published'),
                       created_at, updated_at, 0, 0, 1, 'local'
                FROM contents WHERE plugin_type = 'note'
            """)
            
            # Migrate guestbook entries (title→nickname, body→body, meta_json.email→email)
            await self._db.execute("""
                INSERT OR IGNORE INTO guestbook_entries (id, author_id, nickname, body, email, status, created_at, updated_at, raft_term, raft_index, version, node_id)
                SELECT id, author_id, COALESCE(title, ''), COALESCE(body, ''),
                       COALESCE(json_extract(meta_json, '$.email'), ''),
                       COALESCE(status, 'pending'),
                       created_at, updated_at, 0, 0, 1, 'local'
                FROM contents WHERE plugin_type = 'guestbook'
            """)
            
            await self._db.commit()
            
            # Drop legacy contents table
            await self._db.execute("DROP TABLE IF EXISTS contents")
            await self._db.commit()
            
            # Mark migration as done
            await self._db.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES ('migration_002_contents_split', '1')"
            )
            await self._db.commit()
            print("✓ Migration 002: contents table split complete")
        except Exception as e:
            print(f"⚠ Migration 002 failed: {e}")
            await self._db.rollback()

    async def _migrate_fts5(self) -> None:
        """Migration 004: create FTS5 index for blog_posts and populate from existing data.
        
        Idempotent — checks a flag in _meta before running.
        
        Important: SCHEMA already creates blog_posts_fts + triggers on fresh DBs.
        This migration handles OLD databases that pre-date the FTS addition.
        
        For old DBs, Migration 002 runs first (contents → blog_posts), and the
        SCHEMA triggers will have already populated FTS from those INSERTs.
        So here we do a clean rebuild to avoid duplicates.
        """
        # Check if already migrated
        async with self._db.execute(
            "SELECT value FROM _meta WHERE key = 'migration_004_fts5_blog_posts'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return  # Already done
        
        try:
            # Check if FTS table already exists (created by SCHEMA on fresh DB)
            async with self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='blog_posts_fts'"
            ) as cursor:
                fts_exists = await cursor.fetchone() is not None
            
            if not fts_exists:
                # Old DB: create FTS table (triggers already created by SCHEMA)
                await self._db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS blog_posts_fts USING fts5(
                        title, body, tags,
                        content='blog_posts',
                        content_rowid='id'
                    )
                """)
            
            # Rebuild FTS index from scratch to guarantee consistency.
            # This clears any partial data (e.g. from Migration 002 trigger writes)
            # and re-indexes from the authoritative blog_posts table.
            await self._db.execute("""
                DELETE FROM blog_posts_fts
            """)
            await self._db.execute("""
                INSERT INTO blog_posts_fts(rowid, title, body, tags)
                SELECT id, title, body, tags FROM blog_posts
            """)
            
            # Ensure sync triggers exist (idempotent via IF NOT EXISTS)
            await self._db.execute("""
                CREATE TRIGGER IF NOT EXISTS blog_posts_fts_insert AFTER INSERT ON blog_posts BEGIN
                    INSERT INTO blog_posts_fts(rowid, title, body, tags)
                        VALUES (new.id, new.title, new.body, new.tags);
                END
            """)
            await self._db.execute("""
                CREATE TRIGGER IF NOT EXISTS blog_posts_fts_update AFTER UPDATE ON blog_posts BEGIN
                    INSERT INTO blog_posts_fts(blog_posts_fts, rowid, title, body, tags)
                        VALUES ('delete', old.id, old.title, old.body, old.tags);
                    INSERT INTO blog_posts_fts(rowid, title, body, tags)
                        VALUES (new.id, new.title, new.body, new.tags);
                END
            """)
            await self._db.execute("""
                CREATE TRIGGER IF NOT EXISTS blog_posts_fts_delete AFTER DELETE ON blog_posts BEGIN
                    INSERT INTO blog_posts_fts(blog_posts_fts, rowid, title, body, tags)
                        VALUES ('delete', old.id, old.title, old.body, old.tags);
                END
            """)
            
            await self._db.commit()
            
            # Mark migration as done
            await self._db.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES ('migration_004_fts5_blog_posts', '1')"
            )
            await self._db.commit()
            print("✓ Migration 004: FTS5 index for blog_posts rebuilt")
        except Exception as e:
            print(f"⚠ Migration 004 failed: {e}")
            await self._db.rollback()

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
    
    def _validate_table(self, table: str) -> None:
        """Validate table name against whitelist to prevent SQL injection."""
        if table not in self.ALLOWED_TABLES:
            raise ValueError(f"Table not allowed: {table}")
    
    async def get(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        """Read single record"""
        self._validate_table(table)
        async with self._db.execute(
            f"SELECT * FROM {table} WHERE id = ?", (record_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def put(self, table: str, record_id: int, data: Dict[str, Any]) -> int:
        """Write record with log tracking"""
        self._validate_table(table)
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
        self._validate_table(table)
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
        self._validate_table(table)
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
    
    async def compact_log(self, keep_last: int = 1000) -> int:
        """Compact raft log by removing old entries.
        
        Keeps the most recent `keep_last` entries to support:
        - Recent change replay
        - Migration export
        
        Safe to call periodically (e.g. on startup or via cron).
        Returns the number of deleted entries.
        """
        # Find the cutoff index
        async with self._db.execute(
            "SELECT MAX(term * 1000000000 + idx) as max_key FROM _raft_log"
        ) as cursor:
            row = await cursor.fetchone()
            if not row or row['max_key'] is None:
                return 0
        
        # Get current max term+idx for cutoff calculation
        async with self._db.execute(
            "SELECT term, idx FROM _raft_log ORDER BY term DESC, idx DESC LIMIT 1 OFFSET ?",
            (keep_last,)
        ) as cursor:
            cutoff = await cursor.fetchone()
            if not cutoff:
                return 0  # Less than keep_last entries, nothing to compact
        
        # Delete entries before the cutoff
        await self._db.execute(
            "DELETE FROM _raft_log WHERE term < ? OR (term = ? AND idx < ?)",
            (cutoff['term'], cutoff['term'], cutoff['idx'])
        )
        await self._db.commit()
        
        # Return count of deleted entries
        async with self._db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    @property
    def mode(self) -> str:
        return self._mode
