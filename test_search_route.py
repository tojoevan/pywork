#!/usr/bin/env python3
"""测试搜索路由是否正确注册"""
import sys
sys.path.insert(0, '.')

from app.main import WorkbenchApp
import asyncio

async def test_routes():
    app = WorkbenchApp()
    await app.startup()
    
    # 列出所有路由
    routes = []
    for route in app.app.routes:
        if hasattr(route, 'path'):
            methods = getattr(route, 'methods', ['GET'])
            routes.append(f"{list(methods)[0] if methods else 'GET':6} {route.path}")
    
    # 检查搜索路由
    search_routes = [r for r in routes if '/search' in r]
    
    print("所有路由:")
    for r in sorted(routes):
        print(f"  {r}")
    
    print(f"\n搜索相关路由 ({len(search_routes)} 个):")
    for r in search_routes:
        print(f"  {r}")
    
    if not search_routes:
        print("  ❌ 未找到搜索路由!")
    else:
        print("  ✅ 搜索路由已注册")

if __name__ == "__main__":
    asyncio.run(test_routes())
