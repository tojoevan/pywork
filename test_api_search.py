#!/usr/bin/env python3
"""测试 API 返回的 JSON 数据"""
import urllib.request
import urllib.parse
import json

query = "标题"
encoded_query = urllib.parse.quote(query)
url = f"http://localhost:8080/api/search?q={encoded_query}"

print(f"请求: {url}")

try:
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        
        print(f"\n=== API 响应 ===")
        print(f"查询: {data.get('query')}")
        print(f"总数: {data.get('total')}")
        
        results = data.get('results', {})
        print(f"\n博客结果: {len(results.get('blog', []))} 条")
        print(f"微博结果: {len(results.get('microblog', []))} 条")
        print(f"笔记结果: {len(results.get('notes', []))} 条")
        
        # 显示笔记详情
        notes = results.get('notes', [])
        if notes:
            print("\n笔记详情:")
            for n in notes:
                print(f"  id={n.get('id')}, title=\"{n.get('title')}\"")
        else:
            print("\n❌ 笔记结果为空！")
            
except Exception as e:
    print(f"错误: {type(e).__name__}: {e}")
