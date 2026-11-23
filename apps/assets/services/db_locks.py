"""数据库层面的「事务级串行锁」辅助（跨 PostgreSQL / MySQL）。

PG 有事务级 advisory lock（``pg_advisory_xact_lock``），事务一结束自动释放；MySQL 只有
会话级 ``GET_LOCK``，必须在事务**提交后**才能 ``RELEASE_LOCK``——提前释放会让另一个进程
在提交前拿到锁、读到旧数据，照样撞唯一约束。所以这里用上下文管理器把 MySQL 的锁放在
``transaction.atomic()`` 外层：获取 → 事务 → 释放；PG 侧仍由调用方在事务内用 xact lock。

锁名带当前库名前缀：生产各进程连同一个库 → 同一把锁、互相串行；xdist 的
``test_netops_gwN`` 各 worker 库名不同 → 不会互相阻塞。
"""

from contextlib import contextmanager

from django.db import connection

# GET_LOCK 的等待秒数：-1 = 无限等待，与 PG advisory lock 的阻塞语义一致
_MYSQL_LOCK_TIMEOUT = -1


@contextmanager
def mysql_named_lock(name: str):
    """MySQL 下获取会话级命名锁并在离开时释放；其它后端直接放行。"""
    if connection.vendor != "mysql":
        yield
        return

    lock_name = f"{connection.settings_dict['NAME']}:{name}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [lock_name, _MYSQL_LOCK_TIMEOUT])
        row = cursor.fetchone()
        if row is None or row[0] != 1:
            raise RuntimeError(f"没能拿到 MySQL 命名锁 {lock_name!r}（GET_LOCK 返回 {row!r}）")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", [lock_name])
