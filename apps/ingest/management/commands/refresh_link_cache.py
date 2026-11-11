"""刷新大屏链路带宽 Redis 缓存（不落库）。

用法::

    python manage.py refresh_link_cache            # 立即采集并写缓存
    python manage.py refresh_link_cache --check    # 只校验 conf/links.json，不访问 Zabbix / Redis
"""

from django.core.management.base import BaseCommand, CommandError

from ingest.collectors import link_cache
from ingest.collectors.link_config import LinkConfigError, config_path, load_links_config


class Command(BaseCommand):
    help = "采集链路带宽历史并刷新 Redis 缓存（--check 只校验 conf/links.json）"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="只校验配置结构与启用项，不访问 Zabbix / Redis")

    def handle(self, *args, **options):
        try:
            config = load_links_config()
        except LinkConfigError as exc:
            raise CommandError(str(exc)) from exc

        enabled = config.enabled_targets()
        placeholders = [target for target in enabled if target.ifname == "ifname"]
        self.stdout.write(f"配置: {config_path()}")
        self.stdout.write(f"面板: {len(config.panels)} · 链路: {len(config.targets)}（启用 {len(enabled)}）")
        if placeholders:
            self.stdout.write(self.style.WARNING(f"提示: {len(placeholders)} 条链路的 ifname 仍是占位值，采集不到带宽数据"))

        if options["check"]:
            self.stdout.write(self.style.SUCCESS("配置校验通过"))
            return

        try:
            summary = link_cache.refresh_link_cache(config)
        except Exception as exc:
            raise CommandError(f"刷新链路缓存失败: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"缓存已刷新: {summary}"))
