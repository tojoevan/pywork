#!/usr/bin/env python3
"""检查 FastAPI 已注册路由"""
import urllib.request
import json

try:
    # FastAPI 默认 OpenAPI 端点
    with urllib.request.urlopen("http://localhost:8080/openapi.json", timeout=5) as resp:
        data = json.loads(resp.read().decode())
        
    print("=== 已注册路由 ===")
    paths = data.get("paths", {})
    
    # 查找搜索相关路由
    search_routes = [p for p in paths.keys() if "search" in p.lower()]
    print(f"\n搜索相关路由: {search_routes}")
    
    # 显示所有 GET 路由（前20个）
    print("\n所有 GET 路由（前20个）:")
    get_routes = [p for p in paths.keys() if "get" in paths[p]]
    for i, r in enumerate(get_routes[:20]):
        print(f"  {i+1}. {r}")
        
except Exception as e:
    print(f"错误: {e}")
