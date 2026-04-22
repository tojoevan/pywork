#!/usr/bin/env python3
"""获取搜索结果并保存"""
import urllib.request
import urllib.parse

query = "标题"
encoded_query = urllib.parse.quote(query)
url = f"http://localhost:8080/search?q={encoded_query}"

with urllib.request.urlopen(url, timeout=5) as resp:
    body = resp.read().decode('utf-8')
    
    # 保存完整 HTML
    with open("/tmp/search_result.html", "w") as f:
        f.write(body)
    
    print(f"已保存到 /tmp/search_result.html ({len(body)} 字节)")
    
    # 提取关键信息
    import re
    
    # 查找 total 变量
    total_match = re.search(r'找到\s*<strong>(\d+)</strong>\s*个结果', body)
    if total_match:
        print(f"总结果数: {total_match.group(1)}")
    
    # 查找笔记结果区域
    notes_section = re.search(r'📓 笔记.*?<span class="count">\((\d+)\)</span>', body)
    if notes_section:
        print(f"笔记结果数: {notes_section.group(1)}")
    
    # 查找结果项
    result_items = re.findall(r'class="result-item"', body)
    print(f"结果卡片数: {len(result_items)}")
    
    # 查找高亮
    highlights = re.findall(r'<mark>([^<]+)</mark>', body)
    if highlights:
        print(f"高亮关键词: {highlights}")
