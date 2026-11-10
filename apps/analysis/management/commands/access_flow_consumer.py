"""访问流（AccessFlow）的单写者消费进程：从 Redis Stream 取展开结果并入库。

**只能跑一个实例**（消费者组会把消息摊给多个成员，多起一个就变成多写者，
「先查后合并」的前提就没了）——docker-compose 里的 access-flow-consumer 就是这一个。

每条消息 = 一台设备的完整重建；**入库成功才 XACK**，失败不 ack（留在 PEL 等收尸）。
心跳语义、XAUTOCLAIM 时机与 cast 的理由见 handbook/analysis.md
"""

import signal
from logging import getLogger
from typing import cast

from django.core.management.base import BaseCommand

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "访问流单写者消费进程（只能跑一个实例）：XREADGROUP → 重建入库 → XACK"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=500, help="每轮最多取多少条消息（默认 500）")
        parser.add_argument("--block", type=int, default=5000, help="XREADGROUP 阻塞毫秒数（默认 5000）")
        parser.add_argument(
            "--once",
            action="store_true",
            help="处理完当前积压就退出（冒烟/排障用；正常常驻不加）",
        )

    def handle(self, *args, **options):
        from analysis.access_stream import GROUP, STREAM, beat, consumer_name, ensure_group, get_redis

        count, block, once = options["count"], options["block"], options["once"]
        client = get_redis()
        ensure_group(client)
        name = consumer_name()

        stopping = False

        def _stop(signum, _frame):
            # 收到 SIGTERM/SIGINT 只立旗：让当前批次处理完（ack 掉）再退，不截断事务
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        # 启动/退出是给操作者看的，走 BaseCommand 的输出通道而不是 logger：手动执行时
        # 终端直接可见、call_command(stdout=...) 可捕获，也不受 DJANGO_LOG_LEVEL 摆布。
        # 显式 flush：宿主脚本经 uv run 启动时它已注入 PYTHONUNBUFFERED=1，但容器入口
        # / 手工 python 直跑不保证；统一 flush，保证重定向到文件时这一行立即落盘。
        self.stdout.write(f"访问流消费启动: stream={STREAM} group={GROUP} consumer={name}")
        self.stdout.flush()
        beat(client)

        while not stopping:
            # 心跳在每轮**开头**盖：语义是「进程还活着」，读超时走 except 也得盖章，
            # 否则持续失败会让心跳停更、healthcheck 把活着的进程判死。
            beat(client)
            try:
                # xreadgroup 的返回类型是宽 Union（混着 dict / Awaitable 分支）：
                # 运行期形状固定，cast 成真实形状，免得 pyright 逐分支推断报错。
                responses = cast(
                    "list[tuple[str, list[tuple[str, dict]]]] | None",
                    client.xreadgroup(GROUP, name, {STREAM: ">"}, count=count, block=block),
                )
            except Exception:
                logger.exception("XREADGROUP 失败，5 秒后重试")
                if once:
                    break
                import time

                time.sleep(5)
                continue

            for _stream_name, messages in responses or []:
                for message_id, fields in messages:
                    self._process(client, message_id, fields)

            # 收尸：上次没来得及 ack 就退出的成员留下的消息。空闲超 60s 才接管，
            # 避免抢还在正常处理中的批次。
            try:
                claimed = client.xautoclaim(STREAM, GROUP, name, min_idle_time=60_000, start_id="0-0", count=count)
                for message_id, fields in claimed[1] if len(claimed) >= 2 else []:
                    self._process(client, message_id, fields)
            except Exception:
                logger.warning("XAUTOCLAIM 失败（忽略，下一轮再试）", exc_info=True)

            if once:
                break

        self.stdout.write("访问流消费已退出")
        self.stdout.flush()

    def _process(self, client, message_id, fields) -> None:
        from analysis.access_stream import GROUP, STREAM, handle_message

        try:
            created, updated = handle_message(fields)
            client.xack(STREAM, GROUP, message_id)
            logger.info("已入库 %s: +%s ~%s", message_id, created, updated)
        except Exception:
            # 不 ack：消息留在 PEL，等 XAUTOCLAIM 重投；持续失败靠日志暴露
            logger.exception("处理访问流消息失败（不 ack，等待重投）: %s", message_id)
