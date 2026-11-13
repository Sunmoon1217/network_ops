"""投递 / 执行一次大屏采集（``zabbix`` 设备组 / ``autotask`` 工单·SLB·巡检）。

为什么需要它：Celery beat 的 interval 条目在**首次加入时**把 ``last_run_at`` 记为「加入
时刻」（``celery.beat.Entry`` 里 ``last_run_at = last_run_at or default_now()``），第一次
发送要等满一个周期——``DASHBOARD_AUTOTASK_SECONDS`` 默认 600s，意味着 beat 刚起来的前
10 分钟大屏没有工单数据。beat 启动钩子（``entrypoint/beat.sh``）用本命令先补一次，
日常排障也用它，避免再去拼 ``manage.py shell -c``。

用法::

    python manage.py collect_dashboard                # 投递两个源（不阻塞，等 worker 消费）
    python manage.py collect_dashboard autotask       # 只投一个源
    python manage.py collect_dashboard zabbix --sync  # 本进程同步采集（写库仍投递给 worker）

``--sync`` 只把「采集」放在本进程（排障时能直接看到采集异常），落库照旧走
``analysis.write_dashboard``，所以两种模式都需要 broker（Redis）可达。
"""

from django.core.management.base import BaseCommand, CommandError

# 与 collectors/dashboard.py:collect() 的分支一一对应
SOURCES = ("zabbix", "autotask")


class Command(BaseCommand):
    help = "投递（默认）或同步执行一次大屏采集；不带参数 = zabbix + autotask"

    def add_arguments(self, parser):
        parser.add_argument("sources", nargs="*", metavar="source", help=f"数据源，可选 {' / '.join(SOURCES)}；省略 = 全部")
        parser.add_argument(
            "--sync",
            action="store_true",
            help="在本进程同步采集（不走 worker；写库仍投递给 worker）",
        )

    def handle(self, *args, **options):
        from ingest.tasks import collect_dashboard

        sources = list(options["sources"]) or list(SOURCES)
        unknown = [source for source in sources if source not in SOURCES]
        if unknown:
            raise CommandError(f"未知数据源: {', '.join(unknown)}（可选 {' / '.join(SOURCES)}）")

        for source in sources:
            try:
                if options["sync"]:
                    result = collect_dashboard(source)
                    run = result["run"]
                    self.stdout.write(
                        self.style.SUCCESS(f"{source}: 同步采集完成 run={run['status']} metrics={result['metrics']} samples={result['samples']} cases={result['cases']}")
                    )
                    if run["status"] != "success":
                        raise CommandError(f"{source} 采集失败: {run['error']}")
                else:
                    async_result = collect_dashboard.delay(source)
                    self.stdout.write(f"{source}: 已投递 {async_result.id}")
            except CommandError:
                raise
            except Exception as exc:
                raise CommandError(f"{source} 采集投递失败: {exc}") from exc
