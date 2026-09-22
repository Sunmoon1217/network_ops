"""访问流（AccessFlow）的生产者-消费者通道：Redis Stream + 单写者入库。

链路（Celery 与本模块各管一段，标识体系互不混用）::

    celery worker（ingest.rebuild_access_flows，独立队列 access_flow，多进程并行）
        展开一台设备的策略 ──XADD──> access_flow_stream
                                          │
    access_flow_consumer（独立进程，**唯一**写 AccessFlow 的人）
        XREADGROUP → 摘旧上下文+合并入库（一个事务）→ 入库成功才 XACK

为什么单写者：并行**展开**没问题，冲突都在**写库**——同一条访问流可能被多台设备的
策略命中，多个进程同时「先查后合并」会互相覆盖 contexts。只有一个进程写，就可以
沿用先查后合并 + bulk，而不需要 ON CONFLICT / 行锁；代价是入库吞吐上限取决于这
一个进程（本场景单条毫秒级，足够）。

恢复语义：XACK 在事务提交**之后**——消费者崩溃时消息留在 PEL，重启后由
XAUTOCLAIM 接管重投，而 ``handle_message`` 是幂等的（dict 覆盖 + 冗余数组按最终
状态重算），重放不脏数据。

**消费者只能跑一个实例**：消费者组会把消息分摊给多个成员，多起一个就变成多写者，
「先查后合并」的前提就没了。
"""

from __future__ import annotations

import json
import os
import socket
import time
from contextlib import contextmanager
from functools import lru_cache
from logging import getLogger
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings

if TYPE_CHECKING:
    from celery import Task as CeleryTask

logger = getLogger(__name__)

STREAM = "access_flow_stream"
GROUP = "access_flow_consumers"
#: 消费者每轮循环盖一次章，compose 的 healthcheck 据此判断进程还活着
HEARTBEAT_KEY = "access_flow:heartbeat"


@lru_cache(maxsize=1)
def get_redis():
    """进程内共享一个连接池（decode_responses=False：消息体按 bytes 处理）。"""
    import redis

    return redis.from_url(settings.REDIS_URL)


def stream_maxlen() -> int:
    """Stream 硬上限：背压（ACCESS_FLOW_MAX_QUEUE）是主动限流，这个是爆内存的最后防线。"""
    return settings.ACCESS_FLOW_MAX_QUEUE * 4


def backlog() -> int:
    """当前积压的未消费消息数——生产者据此做背压判断。

    Redis 不可达时返回 0（不背压）：真正的失败会在随后的加锁/投递处暴露并转成重试，
    这里不该先把任务打断。
    """
    try:
        return int(get_redis().xlen(STREAM))
    except Exception:
        logger.warning("读取 %s 积压长度失败（按 0 处理）", STREAM, exc_info=True)
        return 0


def ensure_group(client=None) -> None:
    """消费者组不存在就建（mkstream=True：Stream 键本身也一并创建）。"""
    import redis

    client = client or get_redis()
    try:
        client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        logger.info("消费者组 %s/%s 已创建", STREAM, GROUP)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def encode_message(device, flows: list[dict]) -> dict[str, str]:
    """展开结果 → Stream 消息字段。

    载荷压成紧凑 JSON（一台设备最坏十几万组合，分隔符的空白都不该浪费）；设备信息
    在顶层带一份，消费侧回填 contexts 时以此为准（生产者/消费者只认这一个来源）。
    """
    wire = [[list(flow["key"]), list(flow["contexts"].values())] for flow in flows]
    return {
        "device_id": str(device.pk),
        "hostname": device.hostname,
        "flows": json.dumps(wire, separators=(",", ":"), ensure_ascii=False),
    }


def publish(device, flows: list[dict], client=None) -> None:
    client = client or get_redis()
    # redis 8.1 的 xadd 形如 ``fields: Dict[FieldT, EncodableT]``：FieldT/EncodableT 是
    # **值约束 TypeVar**（只认 str/bytes 等预设项）且嵌在不变（invariant）位置——pyright
    # 拒绝从具体的 ``dict[str, str]`` 反推约束项（报 "str is not the same as FieldT"）。
    # 运行期签名完全兼容，cast 掉这个推断限制（与 workflow.py 处理 celery-stubs 同一手法，
    # 优于 ``# type: ignore``）。
    fields = cast("Any", encode_message(device, flows))
    client.xadd(STREAM, fields, maxlen=stream_maxlen(), approximate=True)


def decode_message(fields: dict) -> tuple[int, list[dict]]:
    """消息字段 → ``upsert_flows`` 的输入；contexts 的键在消费侧按 (设备, 策略) 重建。"""

    def text(name: str) -> str:
        raw = fields.get(name, fields.get(name.encode() if isinstance(name, str) else name))
        if raw is None:
            raise ValueError(f"访问流消息缺少字段: {name}")
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    device_id = int(text("device_id"))
    hostname = text("hostname")
    flows: list[dict] = []
    for key, contexts in json.loads(text("flows")):
        context_map = {}
        for context in contexts:
            filled = {**context, "device_id": device_id, "hostname": hostname}
            context_map[f"{device_id}:{filled['policy_pk']}"] = filled
        # 键按九元组原样还原（长度由模型的唯一约束决定，这里不做假设）
        flows.append({"key": tuple(key), "contexts": context_map})
    return device_id, flows


def handle_message(fields: dict) -> tuple[int, int]:
    """消费一条消息：把该设备的访问流状态**同步**成消息里的展开结果。

    ``sync_device`` = 先合并写入、再摘残留，同一事务——整台设备自足，一条消息就是
    完整状态；重复投递 / 乱序重放都收敛到同一份最终状态（两步皆空操作）。
    """
    from ingest.policy_expand import sync_device

    device_id, flows = decode_message(fields)
    return sync_device(device_id, flows)


def request_rebuild(device_id: int) -> None:
    """投递「重建一台设备的访问流」任务。

    broker 不可达只告警不抛出：解析入库已经成功，重建晚一点没关系（``rebuild_access_flows
    --device`` 可以手工补）。开关 ``ACCESS_FLOW_DISPATCH`` 供测试默认关闭——否则
    PolicySaver 每保存一次就把消息发进真实 Redis。
    """
    if not settings.ACCESS_FLOW_DISPATCH:
        return
    from ingest.tasks import rebuild_access_flows

    try:
        # celery-stubs 把 ``@shared_task`` 装饰后的函数仍声明成普通函数
        # （FunctionType，上面没有 .delay）——运行期它其实是 Task 实例。显式 cast 回
        # Task（与 workflow.py 处理 run_config_parsing 的手法一致，优于 ``# type: ignore``）
        cast("CeleryTask", rebuild_access_flows).delay(device_id)
    except Exception:
        logger.warning(
            "投递 AccessFlow 重建失败（可用 rebuild_access_flows 手工补）: device=%s", device_id, exc_info=True
        )


@contextmanager
def device_lock(device_id: int, timeout: int = 600):
    """同设备互斥：``acks_late`` 重投可能让两份任务同时跑，锁挡住后来者。

    ``blocking=False``：拿不到**立刻**返回 False，由调用方决定（转 retry 释放进程），
    不在这里等——等待就是把 worker 进程占死。
    """
    lock = get_redis().lock(f"access_flow:device:{device_id}", timeout=timeout, blocking_timeout=0)
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                # 超过 timeout 后锁已被 Redis 自动释放，release 会失败——任务本身已经
                # 跑完，这里只需别让收尾动作掩盖真实结果
                logger.warning("释放设备锁失败（可能已超时自动释放）: device=%s", device_id, exc_info=True)


def consumer_name() -> str:
    """消费者成员名：主机名 + pid，重启后是新成员（旧成员的 PEL 靠 xautoclaim 收尸）。"""
    return f"{socket.gethostname()}:{os.getpid()}"


def beat(client=None) -> None:
    """盖心跳章（带 TTL，进程死掉后章自然过期）。"""
    client = client or get_redis()
    client.set(HEARTBEAT_KEY, str(time.time()), ex=300)
