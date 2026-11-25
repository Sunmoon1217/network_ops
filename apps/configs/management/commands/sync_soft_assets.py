"""把 GTM / LTM 配置行归并成软资产（T4）。

    python manage.py sync_soft_assets [--type all|domain|lb] [--dry-run]

只读配置行、只写 ``DomainAsset`` / ``LoadBalancerService``；幂等，消失的配置不删资产。
归属与落库分工见 handbook/assets.md「归并链路」。
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from configs.services.softasset.sync import sync_soft_assets


class Command(BaseCommand):
    help = "把 GTM / LTM 配置行归并为域名 / 负载均衡服务资产"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            choices=("all", "domain", "lb"),
            default="all",
            help="归并范围：all（默认）/ domain / lb",
        )
        parser.add_argument("--dry-run", action="store_true", help="只试算增改数，不写库")

    def handle(self, *args, **options):
        with transaction.atomic():
            stats = sync_soft_assets(options["type"])
            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(f"{prefix}软资产归并（{options['type']}）：新增 {stats.created}，更新 {stats.updated}，未变 {stats.unchanged}，跳过 {stats.skipped}")
