"""Django ORM 连接生命周期助手。

MCP 工具跑在 AnyIO 工作线程（每次调用一个短命线程），不像 Django 视图那样
自带 request_finished 时的 close_old_connections——连接会随线程对象滞留到 GC
才关闭（测试库销毁时报 "being accessed by other users" 就是它）。

``with_db_lifecycle`` 在调用前后各补一次 close_old_connections()：
本项目 CONN_MAX_AGE 默认 0，调用结束即关连接，语义与一次 Web 请求的生命周期对齐。
"""

from functools import wraps

from django.db import close_old_connections


def with_db_lifecycle(fn):
    """工具函数的执行包一层数据库连接回收（调用前清坏连接、调用后必关）。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper
