"""访问流（AccessFlow）的单写者消费进程：从 Redis Stream 取展开结果并入库。

**只能跑一个实例**（消费者组会把消息摊给多个成员，多起一个就变成多写者，
「先查后合并」的前提就没了）——docker-compose 里的 access-flow-consumer 就是这一个。

处理语义（见 ``ingest/access_stream.py``）：

- 每条消息 = 一台设备的完整重建，事务内「摘旧上下文 + 写新展开」；
- **入库成功才 XACK**——崩溃时消息留在 PEL，重启后由 XAUTOCLAIM 接管重投，
  而 handle_message 幂等，重放不脏数据；
- 处理失败**不 ack**：留在 PEL 等下一轮收尸，失败会在日志里持续可见。

心跳：每轮循环给 ``access_flow:heartbeat`` 盖章（TTL 300s），compose 的 healthcheck
据死活判断进程是否还活着（光看 PID 不够：死循环卡住时进程还在）。
"""

import signal
from logging import getLogger

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
        from ingest.access_stream import GROUP, STREAM, beat, consumer_name, ensure_group, get_redis

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

        self.stdout.write(f"访问流消费启动: stream={STREAM} group={GROUP} consumer={name}")
        beat(client)

        while not stopping:
            try:
                responses = client.xreadgroup(GROUP, name, {STREAM: ">"}, count=count, block=block)
            except Exception:
                logger.exception("XREADGROUP 失败，5 秒后重试")
                if once:
                    break
                import time

                time.sleep(5)
                continue

            beat(client)
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

    def _process(self, client, message_id, fields) -> None:
        from ingest.access_stream import GROUP, STREAM, handle_message

        try:
            created, updated = handle_message(fields)
            client.xack(STREAM, GROUP, message_id)
            logger.info("已入库 %s: +%s ~%s", message_id, created, updated)
        except Exception:
            # 不 ack：消息留在 PEL，等 XAUTOCLAIM 重投；持续失败靠日志暴露
            logger.exception("处理访问流消息失败（不 ack，等待重投）: %s", message_id)
