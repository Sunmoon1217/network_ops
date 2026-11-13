"""把存量资产（`Device` / `IPAddress` / `Subnet`）登记进统一 CI 主表（T4）。

    python manage.py register_assets                  # 三类全做
    python manage.py register_assets --type device    # device / ip / subnet
    python manage.py register_assets --dry-run        # 只统计，不写库

幂等：重复执行只更新改过名字的 CI，`ci_id` 不变；源记录删除后 CI 不删（与软资产同策略）。
"""

from django.core.management.base import BaseCommand

from assets.models import CIType
from assets.services.existing_asset_registry import register_existing_assets

#: CLI 简写到 CI 类型的映射（`--type` 的取值）
_TYPE_ALIASES = {
    "device": CIType.DEVICE,
    "ip": CIType.IP_ADDRESS,
    "subnet": CIType.SUBNET,
}


class Command(BaseCommand):
    help = "把存量资产（Device / IPAddress / Subnet）登记进统一 CI 主表"

    def add_arguments(self, parser):
        parser.add_argument("--type", choices=("all", *_TYPE_ALIASES), default="all", help="登记范围：all（默认）/ device / ip / subnet")
        parser.add_argument("--dry-run", action="store_true", help="只统计增改数，不写库")

    def handle(self, *args, **options):
        kinds = None if options["type"] == "all" else [_TYPE_ALIASES[options["type"]]]
        result = register_existing_assets(kinds=kinds, dry_run=options["dry_run"])

        prefix = "[dry-run] " if options["dry_run"] else ""
        total_created = total_updated = total_unchanged = 0
        for kind, stats in result.items():
            self.stdout.write(f"{prefix}{kind}: 新增 {stats.created}，更新 {stats.updated}，未变 {stats.unchanged}")
            total_created += stats.created
            total_updated += stats.updated
            total_unchanged += stats.unchanged
        self.stdout.write(f"{prefix}合计：新增 {total_created}，更新 {total_updated}，未变 {total_unchanged}")
