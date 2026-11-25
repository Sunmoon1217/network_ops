"""数据库命名锁辅助：MySQL 的 ``GET_LOCK`` 需在事务提交后释放，故放在 ``atomic()`` 外层。

锁名带库名前缀，xdist 各 worker 库名不同、不会互相阻塞。跨库差异见 handbook/deploy.md。
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
