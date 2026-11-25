"""启动时按需执行数据库迁移（entrypoint 在起 gunicorn 之前调用）。

只在确有未应用迁移时跑 ``migrate --noinput``；「检查 + 迁移」由数据库命名锁串行化
（PG ``pg_advisory_lock`` / MySQL ``GET_LOCK``），其它后端直接报错而非静默不加锁。
为什么必须自己加锁、为什么不用 ``SELECT FOR UPDATE``、PgBouncer 禁忌见
handbook/deploy.md「启动三步」与技能 ``django-drf-gotchas`` 第 2 节。
"""

from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

# PG 的锁用整数标识：任意固定值即可，只要全项目一致；换数字等于换一把锁。
# 0x6E65746F7073 == b"netops" 的十六进制，纯粹为了好认。
MIGRATION_LOCK_ID = 0x6E65746F7073

# MySQL 的命名锁是服务器级字符串（最长 64 字符），与库名无关。
MYSQL_LOCK_NAME = "netops_migrate"
# GET_LOCK 的等待秒数：-1 = 无限等待（MySQL 5.7+ / MariaDB 10.0.2+），与 PG 的阻塞语义一致。
MYSQL_LOCK_TIMEOUT = -1


class Command(BaseCommand):
    help = "有未应用的迁移时执行 migrate（PostgreSQL / MySQL 用数据库自带的命名锁串行化，可多副本同时启动）"

    def handle(self, *args, **options):
        if connection.vendor == "postgresql":
            with self._postgres_lock():
                self._migrate_if_needed(options)
        elif connection.vendor == "mysql":
            with self._mysql_lock():
                self._migrate_if_needed(options)
        else:
            raise ImproperlyConfigured(
                f"migrate_if_needed 只会用 PostgreSQL 的 advisory lock 或 MySQL 的 GET_LOCK 串行化，"
                f"当前后端是 {connection.vendor!r}；请设 MIGRATE_ON_START=0 并自行执行 "
                f"python manage.py migrate。"
            )

    @contextmanager
    def _postgres_lock(self):
        """会话级 advisory lock：必须在**同一条连接**上加锁与解锁。

        这里全程用 Django 默认连接（MigrationExecutor 与 call_command("migrate") 用的也是它），
        所以锁在整个「检查 + 迁移」期间有效；call_command 内部不会关闭连接。
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [MIGRATION_LOCK_ID])
            try:
                yield
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [MIGRATION_LOCK_ID])

    @contextmanager
    def _mysql_lock(self):
        """MySQL 命名锁：同样是会话级，不建库不建表。

        GET_LOCK 返回 1 = 拿到、0 = 等超时、NULL = 出错（如锁名非法）。
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", [MYSQL_LOCK_NAME, MYSQL_LOCK_TIMEOUT])
            row = cursor.fetchone()
            got = row[0] if row else None
            if got != 1:
                raise CommandError(f"没能拿到 MySQL 命名锁 {MYSQL_LOCK_NAME!r}（GET_LOCK 返回 {got!r}）")
            try:
                yield
            finally:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [MYSQL_LOCK_NAME])

    def _migrate_if_needed(self, options):
        """拿到锁之后再判断一次：等锁期间可能已经有别的副本把迁移跑完了。"""
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            self.stdout.write("[migrate_if_needed] 数据库已是最新，跳过迁移")
            return
        self.stdout.write(f"[migrate_if_needed] 检测到 {len(plan)} 个未应用的迁移，开始执行 migrate --noinput")
        call_command("migrate", interactive=False, verbosity=options.get("verbosity", 1))
