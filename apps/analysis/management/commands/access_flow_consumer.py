"""访问流（AccessFlow）的单写者消费进程：从 Redis Stream 取展开结果并入库。

**只能跑一个实例**（消费者组会把消息摊给多个成员，多起一个就变成多写者，
「先查后合并」的前提就没了）——docker-compose 里的 access-flow-consumer 就是这一个。

处理语义（见 ``analysis/access_stream.py``）：

- 每条消息 = 一台设备的完整重建，事务内「摘旧上下文 + 写新展开」；
- **入库成功才 XACK**——崩溃时消息留在 PEL，重启后由 XAUTOCLAIM 接管重投，
  而 handle_message 幂等，重放不脏数据；
- 处理失败**不 ack**：留在 PEL 等下一轮收尸，失败会在日志里持续可见；
- **重投到阈值自动判死**（``ACCESS_FLOW_MAX_DELIVERIES``，投递前检查）：毒消息能把进程
  直接打挂（超大载荷 OOM 是 SIGKILL，连 except 都进不来），只有**处理之前**的检查断得掉
  「重投 → 打挂 → 重启 → 再重投」死循环（2026-10 事故 + 2026-11 复发的形态）。判死 =
  XACK + XDEL + ``critical`` 点名——丢的只是派生缓存快照，需要就
  ``manage.py rebuild_access_flows --device <H>`` 重建。阈值（20）刻意**大于**
  queue_monitor 的告警线（10）：先报警留人工处置窗口，再到点自动判死。

心跳：每轮循环给 ``access_flow:heartbeat`` 盖章（TTL 300s），compose 的 healthcheck
据死活判断进程是否还活着（光看 PID 不够：死循环卡住时进程还在）。
"""

import signal
from logging import getLogger
from typing import cast

from django.conf import settings
from django.core.management.base import BaseCommand

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "访问流单写者消费进程（只能跑一个实例）：XREADGROUP → 重建入库 → XACK"

    def add_arguments(self, parser):
        # count 是**内存上界**：一条消息 = 一台设备整机展开快照（最坏十几万组合、几十 MB），
        # xreadgroup/xautoclaim 一次物化 count 条进内存——2026-10 / 2026-11 两次 OOM 重启
        # 循环都放大在这里（500 条一起拉 = 最坏十几 GB）。吞吐不是瓶颈（低频链路），调大前先想内存。
        parser.add_argument("--count", type=int, default=10, help="每轮最多取多少条消息（默认 10）")
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

        self.stdout.write(f"访问流消费启动: stream={STREAM} group={GROUP} consumer={name}")
        beat(client)

        while not stopping:
            # 心跳在**每轮开头**盖：语义是「进程还活着」，不能等 xreadgroup 成功——
            # 读超时走进 except 分支时也得盖章，否则读持续失败会让心跳停更，
            # healthcheck 把活着的进程判死（反过来心跳新鲜才判死就更拧了）。
            beat(client)
            try:
                # redis 的 xreadgroup 返回类型是宽 Union（XReadGroupResponse 里混着
                # dict 分支，还叠了 Awaitable）——运行期这里拿到的形状固定是
                # [(stream, [(msg_id, fields), ...]), ...]，block 超时时是 None。
                # cast 成真实形状，避免 pyright 对 Union 的每个分支做迭代/解包推断
                # （会错位报成 "int is not iterable"）。优于 ``# type: ignore``。
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
                # 弹出即释放引用：整轮的载荷（每条最坏几十 MB）不该压到整轮结束
                while messages:
                    message_id, fields = messages.pop(0)  # FIFO：同设备多条消息按序生效
                    self._process(client, message_id, fields)

            # 收尸：上次没来得及 ack 就退出的成员留下的消息。空闲超 60s 才接管，
            # 避免抢还在正常处理中的批次。
            try:
                claimed = client.xautoclaim(STREAM, GROUP, name, min_idle_time=60_000, start_id="0-0", count=count)
                pending = list(claimed[1]) if len(claimed) >= 2 else []
                while pending:
                    message_id, fields = pending.pop(0)
                    self._process(client, message_id, fields)
            except Exception:
                logger.warning("XAUTOCLAIM 失败（忽略，下一轮再试）", exc_info=True)

            if once:
                break

        self.stdout.write("访问流消费已退出")

    def _process(self, client, message_id, fields) -> None:
        from analysis.access_stream import GROUP, STREAM, as_str, handle_message

        # 判死检查必须在**处理之前**：毒消息能把进程直接打挂（超大载荷 OOM 是 SIGKILL，
        # 连 except 都进不来），只有投递前检查能断掉「重投 → 打挂 → 重启 → 再重投」的死循环
        # （2026-10 事故 + 2026-11 复发的形态）。查询失败 fail-open：按首次投递照常处理。
        deliveries = self._deliveries(client, message_id)
        max_deliveries = settings.ACCESS_FLOW_MAX_DELIVERIES
        if deliveries is not None and deliveries >= max_deliveries:
            client.xack(STREAM, GROUP, message_id)
            client.xdel(STREAM, message_id)
            raw_host = fields.get(b"hostname", fields.get("hostname"))
            hostname = raw_host.decode() if isinstance(raw_host, bytes) else raw_host
            raw_device = fields.get(b"device_id", fields.get("device_id"))
            logger.critical(
                "访问流消息判死（已投递 %s 次 ≥ 阈值 %s），丢弃并停止重投: message=%s device=%s(%s)。丢的只是派生缓存快照——如需重建：manage.py rebuild_access_flows --device %s",
                deliveries,
                max_deliveries,
                as_str(message_id),
                as_str(raw_device),
                hostname,
                hostname,
            )
            return

        try:
            created, updated = handle_message(fields)
            client.xack(STREAM, GROUP, message_id)
            logger.info("已入库 %s: +%s ~%s", as_str(message_id), created, updated)
        except Exception:
            # 不 ack：消息留在 PEL，等 XAUTOCLAIM 重投；持续失败靠日志暴露，
            # 重投到阈值由上面的判死检查收口
            logger.exception("处理访问流消息失败（不 ack，等待重投）: %s", as_str(message_id))

    def _deliveries(self, client, message_id) -> int | None:
        """这条消息已投递多少次（XPENDING 单条查询）；查不到 / 查询失败返回 None。

        返回 None 时 fail-open（照常处理）：宁可多试一次，也不能把正常消息误判死。
        """
        from analysis.access_stream import GROUP, STREAM, as_str

        try:
            # count 是 redis-py xpending_range 的**必填位置参数**（漏传直接 TypeError，
            # 2026-11 实测踩过——fail-open 会把判死检查整个短路成警告刷屏）；只查这一条，1 即可
            entries = client.xpending_range(STREAM, GROUP, min=message_id, max=message_id, count=1) or []
        except Exception:
            logger.warning("XPENDING 查询投递次数失败（按首次投递处理）: %s", as_str(message_id), exc_info=True)
            return None
        for entry in entries:
            if as_str(entry.get("message_id")) == as_str(message_id):
                return int(entry.get("times_delivered") or 0)
        return None
