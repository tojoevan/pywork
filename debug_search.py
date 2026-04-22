#!/usr/bin/env python3
"""调试搜索功能"""
import sys
sys.path.insert(0, '.')

import asyncio
import sqlite3

async def debug_search():
    # 直接连接数据库检查
    db_path = "./data/pywork.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("=" * 60)
    print("1. 检查 blog_posts 表")
    print("=" * 60)
    cur.execute("SELECT id, title, status FROM blog_posts LIMIT 5")
    rows = cur.fetchall()
    print(f"找到 {len(rows)} 条博客文章:")
    for row in rows:
        print(f"  - id={row['id']}, title={row['title']}, status={row['status']}")
    
    print("\n" + "=" * 60)
    print("2. 检查 microblog_posts 表")
    print("=" * 60)
    cur.execute("SELECT id, content, status FROM microblog_posts LIMIT 5")
    rows = cur.fetchall()
    print(f"找到 {len(rows)} 条微博:")
    for row in rows:
        print(f"  - id={row['id']}, content={row['content'][:50]}..., status={row['status']}")
    
    print("\n" + "=" * 60)
    print("3. 检查 notes 表")
    print("=" * 60)
    cur.execute("SELECT id, title, visibility FROM notes LIMIT 5")
    rows = cur.fetchall()
    print(f"找到 {len(rows)} 条笔记:")
    for row in rows:
        print(f"  - id={row['id']}, title={row['title']}, visibility={row['visibility']}")
    
    print("\n" + "=" * 60)
    print("4. 检查 FTS5 表")
    print("=" * 60)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'")
    fts_tables = cur.fetchall()
    print(f"FTS5 表: {[row['name'] for row in fts_tables]}")
    
    if fts_tables:
        for table in fts_tables:
            table_name = table['name']
            cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cur.fetchall()
            print(f"\n{table_name} 内容 ({len(rows)} 条):")
            for row in rows:
                print(f"  - {dict(row)}")
    
    print("\n" + "=" * 60)
    print("5. 测试 LIKE 搜索")
    print("=" * 60)
    test_query = "test"
    
    # 博客
    cur.execute("SELECT id, title FROM blog_posts WHERE status='published' AND (title LIKE ? OR body LIKE ?) LIMIT 3",
                (f"%{test_query}%", f"%{test_query}%"))
    rows = cur.fetchall()
    print(f"博客 LIKE 搜索 '{test_query}': {len(rows)} 条结果")
    
    # 微博
    cur.execute("SELECT id, content FROM microblog_posts WHERE status='public' AND content LIKE ? LIMIT 3",
                (f"%{test_query}%",))
    rows = cur.fetchall()
    print(f"微博 LIKE 搜索 '{test_query}': {len(rows)} 条结果")
    
    # 笔记
    cur.execute("SELECT id, title FROM notes WHERE visibility='public' AND (title LIKE ? OR body LIKE ?) LIMIT 3",
                (f"%{test_query}%", f"%{test_query}%"))
    rows = cur.fetchall()
    print(f"笔记 LIKE 搜索 '{test_query}': {len(rows)} 条结果")
    
    conn.close()

if __name__ == "__main__":
    asyncio.run(debug_search())
