#!/usr/bin/env python3
"""检查搜索结果页面内容"""
import urllib.request
import urllib.parse
import re

query = "标题"
encoded_query = urllib.parse.quote(query)
url = f"http://localhost:8080/search?q={encoded_query}"

with urllib.request.urlopen(url, timeout=5) as resp:
    body = resp.read().decode('utf-8')
    
    # 提取结果区域
    print("=== 搜索结果页面分析 ===\n")
    
    # 检查各部分结果数量
    blog_match = re.search(r'博客.*?(\d+)\s*条', body, re.DOTALL)
    microblog_match = re.search(r'微博.*?(\d+)\s*条', body, re.DOTALL)
    notes_match = re.search(r'笔记.*?(\d+)\s*条', body, re.DOTALL)
    
    if blog_match:
        print(f"博客结果: {blog_match.group(1)} 条")
    if microblog_match:
        print(f"微博结果: {microblog_match.group(1)} 条")
    if notes_match:
        print(f"笔记结果: {notes_match.group(1)} 条")
    
    # 检查是否有结果卡片
    if 'result-card' in body:
        print("\n✅ 找到结果卡片")
    if '<mark>' in body:
        print("✅ 找到高亮标记")
        
    # 提取笔记标题
    title_match = re.search(r'<h3[^>]*>(.*?)</h3>', body, re.DOTALL)
    if title_match:
        print(f"\n找到标题: {title_match.group(1)[:100]}")
