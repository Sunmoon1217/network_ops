"""启动时按需执行数据库迁移。

由 ``docker/entrypoint.sh`` 在起 gunicorn 之前调用：**只有确实存在未应用的迁移**时才跑
``migrate --noinput``，已经是最新就打印一行跳过——首次部署第一次启动即自动建表，日常重启
不再有固定开销。

为什么是管理命令，而不是 entrypoint 里的两行 shell（``migrate --check || migrate``）：
两个 app 副本同时启动时，双方的 ``--check`` 会**同时**看到「有未应用迁移」，然后一起执行。
Django 自己并不对 migrate 加锁（翻遍 6.1.1 源码，``advisory`` 零命中），并发迁移会撞
``django_migrations`` 的唯一约束、或留下半应用状态。所以这里用 PostgreSQL 的**会话级**
advisory lock 把「检查 + 迁移」整段串行化：先到的副本执行迁移，其余副本在锁上排队，
拿到锁后再检查一次——此时通常已经是最新，直接跳过。

⚠️ 两点边界：
  * advisory lock 只对 PostgreSQL 有；换成别的后端时退化为「不加锁」，与裸 ``migrate`` 等价。
  * 锁只覆盖**走同一个数据库**的进程。多副本各自连同一个库，所以安全；但如果迁移由外部
    发布流水线负责、或要求人工放行，把 ``MIGRATE_ON_START`` 设为 0 即可让 entrypoint 跳过
    本命令（见 ``env/app.env``）。

本命令只做「建表/改表」，不建管理员——``createsuperuser`` 仍要显式执行。
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

# 任意固定整数即可，只要全项目一致；换数字等于换一把锁。
# 0x6E65746F7073 == b"netops" 的十六进制，纯粹为了好认。
MIGRATION_LOCK_ID = 0x6E65746F7073


class Command(BaseCommand):
    help = "有未应用的迁移时执行 migrate（PostgreSQL 下用 advisory lock 串行化，多副本同时启动安全）"

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self._migrate_if_needed(options)
            return
        # 会话级锁：必须在**同一条连接**上加锁与解锁。这里全程用的是 Django 默认连接
        # （MigrationExecutor 与 call_command("migrate") 用的也是它），所以锁在整个
        # 检查 + 迁移期间都有效；call_command 内部不会关闭连接。
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [MIGRATION_LOCK_ID])
            try:
                self._migrate_if_needed(options)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [MIGRATION_LOCK_ID])

    def _migrate_if_needed(self, options):
        """拿到锁之后再判断一次：等锁期间可能已经有别的副本把迁移跑完了。"""
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            self.stdout.write("[migrate_if_needed] 数据库已是最新，跳过迁移")
            return
        self.stdout.write(f"[migrate_if_needed] 检测到 {len(plan)} 个未应用的迁移，开始执行 migrate --noinput")
        call_command("migrate", interactive=False, verbosity=options.get("verbosity", 1))
