#!/usr/bin/env python3
"""检查 status 字段的实际值"""
import sqlite3

db_path = "./data/pywork.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("microblog_posts 所有 status 值")
print("=" * 60)
cur.execute("SELECT DISTINCT status FROM microblog_posts")
for row in cur.fetchall():
    print(f"  - '{row['status']}'")

print("\n" + "=" * 60)
print("notes 所有 visibility 值")
print("=" * 60)
cur.execute("SELECT DISTINCT visibility FROM notes")
for row in cur.fetchall():
    print(f"  - '{row['visibility']}'")

print("\n" + "=" * 60)
print("blog_posts 所有 status 值")
print("=" * 60)
cur.execute("SELECT DISTINCT status FROM blog_posts")
for row in cur.fetchall():
    print(f"  - '{row['status']}'")

print("\n" + "=" * 60)
print("直接查询公开内容")
print("=" * 60)

# 微博 - 检查实际数据
cur.execute("SELECT id, content, status FROM microblog_posts LIMIT 5")
print("\nmicroblog_posts 前 5 条:")
for row in cur.fetchall():
    print(f"  id={row['id']}, status='{row['status']}', content={row['content'][:30]}...")

# 用实际 status 值查询
cur.execute("SELECT id, content, status FROM microblog_posts WHERE status='public' LIMIT 3")
rows = cur.fetchall()
print(f"\nstatus='public' 查询结果: {len(rows)} 条")

# 笔记
cur.execute("SELECT id, title, visibility FROM notes LIMIT 5")
print("\nnotes 前 5 条:")
for row in cur.fetchall():
    print(f"  id={row['id']}, visibility='{row['visibility']}', title={row['title'][:30]}...")

cur.execute("SELECT id, title, visibility FROM notes WHERE visibility='public' LIMIT 3")
rows = cur.fetchall()
print(f"\nvisibility='public' 查询结果: {len(rows)} 条")

conn.close()
