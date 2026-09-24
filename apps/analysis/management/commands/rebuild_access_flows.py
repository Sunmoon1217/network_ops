"""重建访问流（AccessFlow）：按设备投递重建任务，或 --sync 进程内直跑。

用法::

    manage.py rebuild_access_flows --device fw-bj-01      # 投递到 access_flow 队列（默认）
    manage.py rebuild_access_flows --all                  # 全部设备逐台投递
    manage.py rebuild_access_flows --device fw-bj-01 --sync   # 不经 celery/stream，进程内重建

默认走 celery + Redis Stream（生产者展开 → 单写者入库），与在线链路一致；
``--sync`` 直接调 ``policy_expand.rebuild_device``，用于 broker 不可达、或只想快速
修一台设备的场景。投递模式受 ``ACCESS_FLOW_DISPATCH`` 开关控制（测试里默认关）。
"""

from django.core.management.base import BaseCommand, CommandError

from analysis.policy_expand import rebuild_device
from assets.models import Device


class Command(BaseCommand):
    help = "重建访问流（AccessFlow）：默认投递 celery 任务，--sync 则进程内直接重建"

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--device",
            action="append",
            metavar="HOSTNAME",
            help="设备主机名，可重复；同一台设备重复传入会去重",
        )
        target.add_argument("--all", action="store_true", help="所有设备")
        parser.add_argument(
            "--sync",
            action="store_true",
            help="进程内直接重建（不经过 celery 与 Redis Stream，broker 挂了也能用）",
        )

    def handle(self, *args, **options):
        devices = self._resolve(options)
        if options["sync"]:
            total_created = total_updated = 0
            for device in devices:
                created, updated = rebuild_device(device)
                total_created += created
                total_updated += updated
                self.stdout.write(f"  {device.hostname}: +{created} ~{updated}")
            self.stdout.write(self.style.SUCCESS(f"完成（sync）：{len(devices)} 台，+{total_created} ~{total_updated}"))
            return

        # 延迟 import：让测试可以 monkeypatch ingest.access_flow_trigger.request_rebuild
        # （触发器住 ingest——它是 PolicySaver 侧的投递触点，依赖方向只许 analysis → ingest）
        from ingest.access_flow_trigger import request_rebuild

        for device in devices:
            request_rebuild(device.pk)
        self.stdout.write(
            self.style.SUCCESS(
                f"已投递 {len(devices)} 台设备的重建任务（队列 access_flow，"
                "需有 worker 消费；ACCESS_FLOW_DISPATCH=0 时投递为空操作）"
            )
        )

    def _resolve(self, options) -> list[Device]:
        if options["all"]:
            devices = list(Device.objects.order_by("pk"))
        else:
            names: list[str] = options["device"]
            found = {device.hostname: device for device in Device.objects.filter(hostname__in=names)}
            missing = [name for name in names if name not in found]
            if missing:
                raise CommandError("设备不存在: " + ", ".join(missing))
            # 按 pk 去重（同一个 hostname 重复传入只投一次）
            devices = sorted(found.values(), key=lambda device: device.pk)
        if not devices:
            self.stdout.write("没有匹配的设备")
        return devices
