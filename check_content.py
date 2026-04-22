#!/usr/bin/env python3
"""检查公开内容的实际文本"""
import sqlite3

db_path = "./data/pywork.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("公开微博内容")
print("=" * 60)
cur.execute("SELECT id, content, status FROM microblog_posts WHERE status='public'")
rows = cur.fetchall()
for row in rows:
    print(f"id={row['id']}, status={row['status']}")
    print(f"content: {row['content']}")
    print()

print("=" * 60)
print("公开笔记内容")
print("=" * 60)
cur.execute("SELECT id, title, body, visibility FROM notes WHERE visibility='public'")
rows = cur.fetchall()
for row in rows:
    print(f"id={row['id']}, visibility={row['visibility']}")
    print(f"title: {row['title']}")
    print(f"body: {row['body'][:200] if row['body'] else ''}...")
    print()

print("=" * 60)
print("测试 LIKE 搜索")
print("=" * 60)
# 用实际内容中的词测试
cur.execute("SELECT id, content FROM microblog_posts WHERE status='public' AND content LIKE '%的%' LIMIT 1")
row = cur.fetchone()
if row:
    print(f"微博 LIKE '%的%' 找到: id={row['id']}")
else:
    print("微博 LIKE '%的%' 未找到")

conn.close()
