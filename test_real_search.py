#!/usr/bin/env python3
"""测试搜索关键词匹配实际内容"""
import sqlite3

db_path = "./data/pywork.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 测试能匹配实际内容的关键词
for query in ["测试", "笔记", "cs", "标题"]:
    print(f"\n{'='*60}")
    print(f"搜索: '{query}'")
    print('='*60)
    
    # microblog
    cur.execute(
        """SELECT id, content FROM microblog_posts
           WHERE status = 'public' AND content LIKE ?""",
        (f"%{query}%",)
    )
    microblog = cur.fetchall()
    
    # notes
    cur.execute(
        """SELECT id, title, body FROM notes
           WHERE visibility = 'public'
             AND (title LIKE ? OR body LIKE ?)""",
        (f"%{query}%", f"%{query}%")
    )
    notes = cur.fetchall()
    
    print(f"  microblog: {len(microblog)} 条")
    print(f"  notes: {len(notes)} 条")
    print(f"  总计: {len(microblog) + len(notes)} 条")

conn.close()
