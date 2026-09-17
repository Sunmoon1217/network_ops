"""重新解析已保存到 Git 的设备配置，并重跑 Saver 入库。

用途：改了 TTP 模板、补上设备的厂商/型号、或修好某个 Saver 之后，
对已有的 DeviceConfig 重跑一遍整条链路——正常流程只在 DeviceConfig 新建时触发，
重复导入同一 commit 是空操作，所以需要一个显式入口。

    python manage.py reparse --device sw-bj-01
    python manage.py reparse --device sw-bj-01 --device fw-bj-01
    python manage.py reparse --all
    python manage.py reparse --all --no-parse     # 只重跑 Saver，沿用已有 config_json
"""

from django.core.management.base import BaseCommand, CommandError

from assets.models import Device, DeviceConfig
from ops.pipeline import run_config_pipeline


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

    def handle(self, *args, **options):
        configs = self._pick_configs(options)
        if not configs:
            self.stdout.write(self.style.WARNING("没有找到符合条件的 DeviceConfig"))
            return

        force_parse = not options["no_parse"]
        failed = 0
        skipped = 0

        for config in configs:
            hostname = config.device.hostname
            result = run_config_pipeline(config.device, config, force_parse=force_parse)

            if result.skipped:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"{hostname}: 跳过（{result.skipped}）"))
                continue

            mode = "已重新解析" if result.parsed else "沿用 config_json"
            self.stdout.write(f"{hostname}: {mode}，顶层 key {len(result.config_json)} 个")
            for outcome in result.outcomes:
                if outcome.error:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"  [{outcome.label}] 失败: {outcome.error}"))
                else:
                    self.stdout.write(f"  [{outcome.label}] +{outcome.created} ~{outcome.updated}")

        self.stdout.write("")
        self.stdout.write(f"完成：{len(configs)} 台设备，{failed} 个 Saver 失败，{skipped} 台跳过")

        if failed:
            # 用非零退出码收尾，方便脚本 / CI 判断结果
            raise CommandError(f"{failed} 个 Saver 执行失败")

    def _pick_configs(self, options) -> list[DeviceConfig]:
        queryset = DeviceConfig.objects.select_related("device").order_by("device__hostname", "-pk")

        if options["all"]:
            # 每台设备只取最新一条，避免把历史版本全部重跑一遍
            latest: dict[int, DeviceConfig] = {}
            for config in queryset:
                latest.setdefault(config.device_id, config)
            return list(latest.values())

        found: dict[str, DeviceConfig] = {}
        for hostname in options["device"] or []:
            device = Device.objects.filter(hostname=hostname).first()
            if not device:
                raise CommandError(f"设备不存在: {hostname}")
            config = queryset.filter(device=device).first()
            if not config:
                raise CommandError(f"设备 {hostname} 没有 DeviceConfig 记录（配置还没保存到 Git？）")
            found[hostname] = config
        return [found[hostname] for hostname in options["device"]]
