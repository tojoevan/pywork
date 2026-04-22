#!/usr/bin/env python3
"""检查数据库中的实际内容"""
import sqlite3

db_path = "./data/pywork.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("1. 博客文章 (blog_posts)")
print("=" * 60)
cur.execute("SELECT id, title, status, author_id FROM blog_posts ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()
print(f"总数: {len(rows)} 条")
for row in rows:
    print(f"  id={row['id']}, status={row['status']}, title={row['title'][:40]}...")

print("\n" + "=" * 60)
print("2. 微博 (microblog_posts)")
print("=" * 60)
cur.execute("SELECT id, content, status FROM microblog_posts ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()
print(f"总数: {len(rows)} 条")
for row in rows:
    content = row['content'][:50] if row['content'] else ""
    print(f"  id={row['id']}, status={row['status']}, content={content}...")

print("\n" + "=" * 60)
print("3. 笔记 (notes)")
print("=" * 60)
cur.execute("SELECT id, title, visibility FROM notes ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()
print(f"总数: {len(rows)} 条")
for row in rows:
    print(f"  id={row['id']}, visibility={row['visibility']}, title={row['title'][:40]}...")

print("\n" + "=" * 60)
print("4. 统计")
print("=" * 60)
cur.execute("SELECT COUNT(*) as cnt FROM blog_posts WHERE status='published'")
print(f"已发布博客: {cur.fetchone()['cnt']}")

cur.execute("SELECT COUNT(*) as cnt FROM microblog_posts WHERE status='public'")
print(f"公开微博: {cur.fetchone()['cnt']}")

cur.execute("SELECT COUNT(*) as cnt FROM notes WHERE visibility='public'")
print(f"公开笔记: {cur.fetchone()['cnt']}")

conn.close()
