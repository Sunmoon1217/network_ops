"""队列积压巡检命令：celery 队列 + 访问流 Stream + 消费者心跳，只读、不干预。

命令本体在 core（运维命令统一放 core：ensure_superuser / migrate_if_needed / queue_*），
采集逻辑仍共用 ``analysis.queue_monitor``（API / 前端卡片同源）——core 的运维命令
跨域 import analysis 与 ``purge_configs`` 同属运维工具例外。
本命令的增量价值是**阈值退出码**：超阈值退出码 1，可以直接接 cron / 告警脚本::

    # cron 示例：每分钟巡检，非 0 就把输出喂给告警
    * * * * * python manage.py queue_status --json >> /var/log/netops/queue.log || <告警动作>

用法::

    python manage.py queue_status              # 人看表格
    python manage.py queue_status --json       # 机器可读（含 thresholds / alerts）
    python manage.py queue_status --max-queue 100 --max-stream-lag 50   # 覆盖阈值

退出码：0 = 无告警；1 = 有告警（含 Redis 不可达）。
"""

import json
import sys

from django.core.management.base import BaseCommand

from analysis.queue_monitor import DEFAULT_THRESHOLDS, collect


class Command(BaseCommand):
    help = "巡检 celery 队列与访问流 Stream 的积压（只读；超阈值退出码 1，可接 cron 告警）"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读，含告警与阈值）")
        parser.add_argument("--max-queue", type=int, help=f"单队列积压告警阈值（默认 {DEFAULT_THRESHOLDS['max_queue']}）")
        parser.add_argument("--max-unacked", type=int, help=f"执行中未确认告警阈值（默认 {DEFAULT_THRESHOLDS['max_unacked']}）")
        parser.add_argument("--max-stream-lag", type=int, help=f"Stream 未消费积压告警阈值（默认 {DEFAULT_THRESHOLDS['max_stream_lag']}）")
        parser.add_argument("--max-pending", type=int, help=f"PEL 待确认告警阈值（默认 {DEFAULT_THRESHOLDS['max_pending']}）")
        parser.add_argument("--max-deliveries", type=int, help=f"单条消息重投次数告警阈值（默认 {DEFAULT_THRESHOLDS['max_deliveries']}）")
        parser.add_argument("--heartbeat-stale", type=int, help=f"心跳过期告警阈值秒数（默认 {DEFAULT_THRESHOLDS['heartbeat_stale']}）")

    def handle(self, *args, **options):
        thresholds = {
            key: options[flag]
            for key, flag in (
                ("max_queue", "max_queue"),
                ("max_unacked", "max_unacked"),
                ("max_stream_lag", "max_stream_lag"),
                ("max_pending", "max_pending"),
                ("max_deliveries", "max_deliveries"),
                ("heartbeat_stale", "heartbeat_stale"),
            )
            if options[flag] is not None
        }
        stats = collect(thresholds=thresholds or None)

        if options["json"]:
            self.stdout.write(json.dumps(stats, ensure_ascii=False))
        else:
            self._render(stats)

        for alert in stats["alerts"]:
            # 告警同时落日志：cron 场景下即使丢弃 stdout，日志里也持续可见
            self.stdout.write(f"[{alert['level']}] {alert['message']}")
        if stats["alerts"] or not stats["redis_ok"]:
            sys.exit(1)

    def _render(self, stats: dict) -> None:
        """人看的表格（对齐列宽，阈值随行标注）。"""
        if not stats["redis_ok"]:
            self.stdout.write(f"Redis 不可达: {stats['error']}")
            return
        t = stats["thresholds"]

        self.stdout.write("celery 队列（排队未执行）:")
        for name, length in stats["queues"].items():
            self.stdout.write(f"  {name:<20} {length:>8} 条")
        self.stdout.write(f"  {'执行中未确认(unacked)':<20} {stats['unacked']:>8} 条  (阈值 {t['max_unacked']})")

        stream = stats["stream"] or {}
        backlog = stream.get("lag") if stream.get("lag") is not None else stream.get("xlen", 0)
        self.stdout.write("访问流 Stream:")
        self.stdout.write(f"  {'未消费积压(lag)':<20} {backlog:>8} 条  (阈值 {t['max_stream_lag']})")
        self.stdout.write(f"  {'待确认(PEL)':<20} {stream.get('pending', 0):>8} 条  (阈值 {t['max_pending']})")
        self.stdout.write(f"  {'总条数(xlen)':<20} {stream.get('xlen', 0):>8} 条  (含已消费未 trim)")
        self.stdout.write(f"  {'组内消费者':<20} {stream.get('consumers', 0):>8} 个")

        heartbeat = stats.get("heartbeat_age")
        label = "缺失" if heartbeat is None else f"{int(heartbeat)}s 前"
        self.stdout.write(f"  {'消费者心跳':<20} {label:>8}     (过期阈值 {t['heartbeat_stale']}s)")

        for entry in stream.get("top_pending") or []:
            self.stdout.write(f"  重投最多: {entry['id']} 已投 {entry['deliveries']} 次, 空闲 {entry['idle_ms'] // 1000}s")
