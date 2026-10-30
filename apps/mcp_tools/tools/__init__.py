"""按域分模块的 MCP 工具实现。

每个模块暴露 ``register(mcp)``，工具函数写在其中：
同步 def（SDK v2 在工作线程执行，Django ORM 同步 API 直接可用；
不要改成 async def——事件循环里调 ORM 会触发 SynchronousOnlyOperation）。
"""
