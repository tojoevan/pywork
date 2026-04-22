#!/usr/bin/env python3
"""直接 HTTP 请求测试（URL 编码）"""
import urllib.request
import urllib.parse
import urllib.error

# URL 编码中文
query = "标题"
encoded_query = urllib.parse.quote(query)
url = f"http://localhost:8080/search?q={encoded_query}"

print(f"查询: {query}")
print(f"URL: {url}")

try:
    req = urllib.request.Request(url)
    req.add_header('Accept', 'text/html')
    
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"\n状态码: {resp.status}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        body = resp.read().decode('utf-8')
        print(f"响应长度: {len(body)} 字节")
        
        # 检查是否包含搜索结果
        if "笔记" in body or query in body:
            print("\n✅ 搜索结果包含关键词！")
        else:
            print("\n❌ 搜索结果不包含关键词")
            
        # 显示关键部分
        if "notes_results" in body:
            print("找到 notes_results 区域")
        if '<mark>' in body:
            print("找到高亮标记 <mark>")
            
except urllib.error.HTTPError as e:
    print(f"HTTP 错误: {e.code} {e.reason}")
    body = e.read().decode('utf-8', errors='ignore')
    print(f"响应体前500字符:\n{body[:500]}")
except Exception as e:
    print(f"错误: {type(e).__name__}: {e}")
