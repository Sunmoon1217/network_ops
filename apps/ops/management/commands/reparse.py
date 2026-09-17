"""重新解析已保存到 Git 的设备配置，并重跑 Saver 入库。

用途：改了 TTP 模板、补上设备的厂商/型号、或修好某个 Saver 之后，
对已有的 DeviceConfig 重跑一遍整条链路——正常流程只在 DeviceConfig 新建时触发，
重复导入同一 commit 是空操作，所以需要一个显式入口。

    python manage.py reparse --device sw-bj-01
    python manage.py reparse --device sw-bj-01 --device fw-bj-01
    python manage.py reparse --all
    python manage.py reparse --all --no-parse     # 只重跑 Saver，沿用已有 config_json
    python manage.py reparse --all --workers 4    # 跨设备并行

``--workers`` 的并行单位是**设备**：解析（TTP）与 Saver 里的 DRF 校验都是 CPU
密集型，进程比线程更能扩展，所以用进程池而不是线程池。每个设备只派一个任务，
任务之间没有共享行，因此并行不会让它们互相写坏。

⚠️ 只保证「本命令内部」不会让同一台设备并发。信号路径（Web 导入配置）没有
设备级互斥，如果一边跑 reparse 一边有请求导入同一台设备，两边仍会同时写同一批行。
"""

import multiprocessing

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from assets.models import Device, DeviceConfig


def _run_one(config_pk: int, force_parse: bool) -> dict:
    """按 pk 取 DeviceConfig 并跑完整流水线，返回可序列化的摘要。

    不碰数据库连接：顺序路径与测试都跑在调用方的连接/事务里，
    连接的生命周期由 ``_run_one_in_child`` 专门管理。
    """
    from ops.pipeline import run_config_pipeline

    config = DeviceConfig.objects.select_related("device").get(pk=config_pk)
    result = run_config_pipeline(config.device, config, force_parse=force_parse)
    return {
        "hostname": config.device.hostname,
        "parsed": result.parsed,
        "key_count": len(result.config_json),
        "skipped": result.skipped,
        "outcomes": [
            {"label": o.label, "created": o.created, "updated": o.updated, "error": o.error}
            for o in result.outcomes
        ],
    }


def _run_one_in_child(task: tuple[int, bool]) -> dict:
    """进程池入口（必须是模块顶层函数才能被 pickle）。

    子进程不能用父进程 fork 过来的那条数据库连接，所以进来先关掉、结束再关掉自己的。
    """
    config_pk, force_parse = task
    connections.close_all()
    try:
        return _run_one(config_pk, force_parse)
    except Exception as e:
        # 子进程里直接抛出去只会被池吞掉、丢掉设备名，这里转成摘要带回去
        return {
            "hostname": f"pk={config_pk}",
            "parsed": False,
            "key_count": 0,
            "skipped": "",
            "outcomes": [],
            "fatal": str(e),
        }
    finally:
        connections.close_all()


class Command(BaseCommand):
    help = "重新解析已保存到 Git 的设备配置，并重跑 Saver 入库"

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--device", action="append", metavar="HOSTNAME", help="设备主机名，可重复指定")
        target.add_argument("--all", action="store_true", help="所有持有配置的设备（每台取最新一条）")
        parser.add_argument(
            "--no-parse",
            action="store_true",
            help="只重跑 Saver，沿用已有 config_json，不重新解析",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            metavar="N",
            help="跨设备并行度，默认 1（顺序执行）。每台设备只会被一个 worker 处理",
        )

    def handle(self, *args, **options):
        configs = self._pick_configs(options)
        if not configs:
            self.stdout.write(self.style.WARNING("没有找到符合条件的 DeviceConfig"))
            return

        if options["workers"] < 1:
            raise CommandError("--workers 必须 >= 1")

        workers = min(options["workers"], len(configs))
        force_parse = not options["no_parse"]

        if workers > 1:
            summaries = self._run_parallel(configs, force_parse, workers)
        else:
            summaries = [self._run_sequential(config, force_parse) for config in configs]

        failed = 0
        skipped = 0
        for summary in summaries:
            hostname = summary["hostname"]
            if summary.get("fatal"):
                failed += 1
                self.stdout.write(self.style.ERROR(f"{hostname}: 执行失败: {summary['fatal']}"))
                continue
            if summary["skipped"]:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"{hostname}: 跳过（{summary['skipped']}）"))
                continue

            mode = "已重新解析" if summary["parsed"] else "沿用 config_json"
            self.stdout.write(f"{hostname}: {mode}，顶层 key {summary['key_count']} 个")
            for outcome in summary["outcomes"]:
                if outcome["error"]:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"  [{outcome['label']}] 失败: {outcome['error']}"))
                else:
                    self.stdout.write(f"  [{outcome['label']}] +{outcome['created']} ~{outcome['updated']}")

        self.stdout.write("")
        suffix = f"，并行度 {workers}" if workers > 1 else ""
        self.stdout.write(f"完成：{len(configs)} 台设备，{failed} 个 Saver 失败，{skipped} 台跳过{suffix}")

        if workers == 1 and len(configs) > 1:
            self.stdout.write(self.style.HTTP_INFO("提示：加 --workers N 可以跨设备并行（每台设备只派一个任务）"))

        if failed:
            # 用非零退出码收尾，方便脚本 / CI 判断结果
            raise CommandError(f"{failed} 个 Saver 执行失败")

    def _run_sequential(self, config: DeviceConfig, force_parse: bool) -> dict:
        """顺序路径复用同一份逻辑，保证两条路径语义与输出完全一致"""
        return _run_one(config.pk, force_parse)

    def _run_parallel(self, configs: list[DeviceConfig], force_parse: bool, workers: int) -> list[dict]:
        """进程池跑，结果按完成顺序即时打印，返回值按完成顺序排列"""
        # 父进程的连接不能带进 fork 出来的子进程
        connections.close_all()
        tasks = [(config.pk, force_parse) for config in configs]
        results: list[dict] = []

        # fork：子进程直接继承已初始化的 Django 环境，不必重新 setup
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(processes=workers) as pool:
            for summary in pool.imap_unordered(_run_one_in_child, tasks):
                results.append(summary)
                # 完成一台就报一台，不必等最慢的那台
                self.stdout.write(f"  ✓ {summary['hostname']}")
        return results

    def _pick_configs(self, options) -> list[DeviceConfig]:
        """选出待处理的 DeviceConfig，保证**每台设备最多一条**"""
        queryset = DeviceConfig.objects.select_related("device").order_by("device__hostname", "-pk")

        if options["all"]:
            # 每台设备只取最新一条，避免把历史版本全部重跑一遍
            latest: dict[int, DeviceConfig] = {}
            for config in queryset:
                latest.setdefault(config.device_id, config)
            return list(latest.values())

        # 同一个 hostname 传多次会拿到同一条配置：不按设备去重的话，
        # 并行时就会有多个 worker 同时写同一台设备
        found: dict[str, DeviceConfig] = {}
        ordered: list[str] = []
        for hostname in options["device"] or []:
            if hostname in found:
                continue
            device = Device.objects.filter(hostname=hostname).first()
            if not device:
                raise CommandError(f"设备不存在: {hostname}")
            config = queryset.filter(device=device).first()
            if not config:
                raise CommandError(f"设备 {hostname} 没有 DeviceConfig 记录（配置还没保存到 Git？）")
            found[hostname] = config
            ordered.append(hostname)
        return [found[hostname] for hostname in ordered]
