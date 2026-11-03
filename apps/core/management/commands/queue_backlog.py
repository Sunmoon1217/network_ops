"""积压明细命令：看「积压了哪些」——各队列排队消息 + 访问流 Stream 的点名清单。

与 ``queue_status``（数量 + 告警 + 退出码）互补：那个答「堆了多少、超没超阈值」，
本命令答「堆的是什么」。采集逻辑在 ``analysis.queue_monitor.collect_backlog``
（与 API 同源），本命令只做渲染。

用法::

    python manage.py queue_backlog                 # 人看明细（每清单默认 20 条）
    python manage.py queue_backlog --limit 50      # 每清单条数
    python manage.py queue_backlog --json          # 机器可读

清单三段：

- celery 队列排队消息：任务名 / id / 参数预览（broker 消息解不动按原文截断）；
- Stream 待确认（PEL）：消息 ID / 设备 / 空闲秒数 / **重投次数**（重投高 = 毒消息）；
- Stream 未投递积压：消息 ID / 设备（lag 口径，不含已消费未 trim 的旧条目）。

只读、不干预：不删消息、不 XACK、不 revoke。
"""

import json

from django.core.management.base import BaseCommand

from analysis.queue_monitor import collect_backlog


class Command(BaseCommand):
    help = "看积压明细（只读）：队列排队消息 + 访问流 Stream 待确认/未投递的点名清单"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="每个清单最多显示条数（默认 20）")
        parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")

    def handle(self, *args, **options):
        stats = collect_backlog(limit=options["limit"])
        if options["json"]:
            self.stdout.write(json.dumps(stats, ensure_ascii=False))
        else:
            self._render(stats)

    def _render(self, stats: dict) -> None:
        if not stats["redis_ok"]:
            self.stdout.write(f"Redis 不可达: {stats['error']}")
            return
        limit = stats["limit"]

        self.stdout.write(f"celery 队列排队消息（每个队列最多 {limit} 条）:")
        for name, items in stats["queues"].items():
            self.stdout.write(f"  [{name}] {len(items)} 条")
            for item in items:
                task = item["task"] or "<任务名缺失>"
                suffix = "（解码失败，原文预览）" if item["decode_error"] else ""
                self.stdout.write(f"    {task}  id={item['id'] or '-'}  args={item['args'] or '-'}{suffix}")

        stream = stats["stream"]
        self.stdout.write(f"\n访问流 Stream · 待确认（PEL，最多 {limit} 条，重投高=毒消息）:")
        if not stream["pending"]:
            self.stdout.write("  （无）")
        for entry in stream["pending"]:
            host = entry["hostname"] or f"device {entry['device_id']}"
            self.stdout.write(
                f"  {entry['id']}  {host}  空闲 {entry['idle_ms'] // 1000}s  已重投 {entry['deliveries']} 次"
            )

        self.stdout.write(f"\n访问流 Stream · 未投递积压（lag 口径，最多 {limit} 条）:")
        if not stream["undelivered"]:
            self.stdout.write("  （无）")
        for entry in stream["undelivered"]:
            host = entry["hostname"] or f"device {entry['device_id']}"
            self.stdout.write(f"  {entry['id']}  {host}")
