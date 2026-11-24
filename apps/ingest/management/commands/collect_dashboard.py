"""投递 / 执行一次大屏采集（``zabbix`` 设备组 / ``autotask`` 工单·SLB·巡检）。

beat 首次加入 interval 条目要等满一个周期才发，``entrypoint/beat.sh`` 用本命令先补一次；
日常排障也用它。

    python manage.py collect_dashboard                # 投递两个源（不阻塞）
    python manage.py collect_dashboard autotask       # 只投一个源
    python manage.py collect_dashboard zabbix --sync  # 本进程同步采集（写库仍投给 worker）

两种模式都需要 broker（Redis）可达。
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
                    async_result = collect_dashboard.delay(source)  # type: ignore[attr-defined]
                    self.stdout.write(f"{source}: 已投递 {async_result.id}")
            except CommandError:
                raise
            except Exception as exc:
                raise CommandError(f"{source} 采集投递失败: {exc}") from exc
