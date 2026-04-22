#!/usr/bin/env python3
"""测试搜索查询"""
import sqlite3

db_path = "./data/pywork.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

query = "测试"  # 使用中文关键词

print("=" * 60)
print(f"搜索关键词: '{query}'")
print("=" * 60)

# 测试 microblog LIKE 查询
print("\n[microblog] LIKE 查询:")
cur.execute(
    """SELECT id, author_id, content, created_at
       FROM microblog_posts
       WHERE status = 'public' AND content LIKE ?
       ORDER BY created_at DESC
       LIMIT 20""",
    (f"%{query}%",)
)
rows = cur.fetchall()
print(f"  结果: {len(rows)} 条")
for row in rows:
    print(f"    - id={row['id']}, content={row['content'][:50]}...")

# 测试 notes LIKE 查询
print("\n[notes] LIKE 查询:")
cur.execute(
    """SELECT id, author_id, title, body, visibility, created_at
       FROM notes
       WHERE visibility = 'public'
         AND (title LIKE ? OR body LIKE ?)
       ORDER BY created_at DESC
       LIMIT 20""",
    (f"%{query}%", f"%{query}%")
)
rows = cur.fetchall()
print(f"  结果: {len(rows)} 条")
for row in rows:
    print(f"    - id={row['id']}, title={row['title']}, body={row['body'][:50]}...")

# 检查实际内容
print("\n" + "=" * 60)
print("实际内容检查:")
print("=" * 60)

cur.execute("SELECT id, content FROM microblog_posts WHERE status='public'")
print("\nmicroblog 公开内容:")
for row in cur.fetchall():
    print(f"  id={row['id']}: {row['content']}")

cur.execute("SELECT id, title, body FROM notes WHERE visibility='public'")
print("\nnotes 公开内容:")
for row in cur.fetchall():
    print(f"  id={row['id']}: title={row['title']}, body={row['body']}")

conn.close()
