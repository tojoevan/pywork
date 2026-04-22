#!/usr/bin/env python3
"""直接测试搜索 SQL 查询"""
import sqlite3
import asyncio
import sys
sys.path.insert(0, '.')

async def test_search():
    from app.storage import SQLiteEngine
    
    engine = SQLiteEngine("./data/pywork.db")
    await engine.start()
    
    query = "标题"
    
    # 测试 notes 搜索
    results = await engine.fetchall(
        """SELECT id, author_id, title, body, visibility, created_at
           FROM notes
           WHERE visibility = 'public'
             AND (title LIKE ? OR body LIKE ?)
           ORDER BY created_at DESC
           LIMIT 20""",
        (f"%{query}%", f"%{query}%")
    )
    
    print(f"搜索 '{query}' 在 notes 表:")
    print(f"找到 {len(results)} 条结果")
    for r in results:
        print(f"  id={r['id']}, title=\"{r['title']}\", visibility=\"{r['visibility']}\"")
    
    await engine.stop()

if __name__ == "__main__":
    asyncio.run(test_search())
