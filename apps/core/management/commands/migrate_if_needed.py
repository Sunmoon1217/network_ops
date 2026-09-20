"""启动时按需执行数据库迁移。

由 ``docker/entrypoint.sh`` 在起 gunicorn 之前调用：**只有确实存在未应用的迁移**时才跑
``migrate --noinput``，已经是最新就打印一行跳过——首次部署第一次启动即自动建表，日常重启
不再有固定开销。

为什么是管理命令，而不是 entrypoint 里的两行 shell（``migrate --check || migrate``）：
两个 app 副本同时启动时，双方的 ``--check`` 会**同时**看到「有未应用迁移」，然后一起执行。
Django 自己并不对 migrate 加锁（翻遍 6.1.1 源码，``advisory`` 零命中），并发迁移会撞
``django_migrations`` 的唯一约束、或留下半应用状态。所以这里用**数据库自带的命名锁**把
「检查 + 迁移」整段串行化：先到的副本执行迁移，其余副本在锁上排队，拿到锁后再检查一次
——此时通常已经是最新，直接跳过。

按后端分派（``connection.vendor``）：

* ``postgresql``：会话级 **advisory lock**（``pg_advisory_lock`` / ``pg_advisory_unlock``）。
  会话断开即释放，没有 TTL、不建表、不用写 catalog。
* ``mysql``（含 MariaDB）：**命名锁** ``GET_LOCK`` / ``RELEASE_LOCK``。同样是服务器级的
  会话锁，不建库不建表，``IS_USED_LOCK()`` 与 ``performance_schema.metadata_locks`` 能看到
  谁持有；``GET_LOCK`` 的第二个参数是等待秒数，这里用 -1（无限等待，5.7+ / MariaDB 10.0.2+），
  与 PG 的阻塞语义对齐。
* 其它后端：**直接报错**，不再「退化成不加锁」——SQLite 是进程内嵌库、单实例部署下不需要锁，
  而"看上去有锁其实没锁"是最坏的形态。真要跑，就设 ``MIGRATE_ON_START=0`` 自己执行 migrate。

为什么不用「手写锁」：``SELECT ... FOR UPDATE`` 与 ``LOCK TABLE`` 都要求把整段 migrate 关进
一个事务（PG 里 ``LOCK TABLE`` 在自动提交下直接报错，行锁则在空表上无处可加），会连带禁掉
``AddIndexConcurrently`` 这类 ``atomic = False`` 的迁移；而「锁表 + 插入一行」或「CREATE TABLE
当锁」在崩溃后必然残留，且没有任何持有者/时间信息可供超时接管——最后一定会演化成 Flyway 的
``DATABASECHANGELOGLOCK``（锁表 + 心跳 + 手动解锁）。引擎自带的命名锁把「崩溃自动释放」白送，
这才是选它的理由。

⚠️ 两个边界：
  * 锁只覆盖**走同一个数据库服务器**的进程。多副本各自连同一个库，所以安全；迁移若由外部
    发布流水线负责、或要求人工放行，把 ``MIGRATE_ON_START`` 设为 0 即可（见 ``env/app.env``）。
  * **PG 前面不要挂 PgBouncer 的 transaction pooling**：官方特性表明确写着 ``Session-level
    advisory locks`` 在 transaction pooling 下是 *Never*——事务一结束连接就被回收，
    ``pg_advisory_unlock`` 可能发到另一个后端上。现在 app 是直连 db、没有 pooler，不受影响。

本命令只做「建表/改表」，不建管理员——``createsuperuser`` 仍要显式执行。
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
            got = cursor.fetchone()[0]
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
