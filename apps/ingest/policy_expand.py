"""策略展开：把 Policy 的 src/dst/service 三个 M2M 展开成访问流（AccessFlow）并合并入库。

一条策略的三个维度是笛卡尔积（7×7×7 ≈ 343 行/策略），但**同一条访问流可能出现在
多台设备、多条策略上**——所以唯一键是归一化后的九元组（地址每侧 ip/prefix/range_end
三段 + protocol/port/port2 三段，见 ``AccessFlow``）， ``(device_id, policy_pk)`` 作为
上下文聚进同一行的 ``contexts``（dict，键 ``"<device_id>:<policy_pk>"``）。

contexts 的键语义（别改坏）：

- 键带的是**策略主键**，不是内容——同一台设备上内容重复的两条策略会各占一个键、
  互不覆盖，这正是「设备内重复策略 / 多开」审计的数据来源；
- 重跑/重放时同键覆盖（策略改了内容会更新），不同键各自保留，幂等；
- 摘除按设备前缀（``f"{device_id}:"``）整体剥离，见 ``remove_device_context``。

写库方式是**先查后合并 + bulk_create/bulk_update**（不是 update_or_create——逐行
往返在万级策略下不可用）。这条路径是给**单写者**用的（见 ``ingest/access_stream.py``：
只有 access_flow_consumer 一个进程写 AccessFlow），所以不需要 ON CONFLICT / 行锁。
"""

from __future__ import annotations

import ipaddress
from itertools import product
from logging import getLogger
from typing import Any, Iterable

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from ingest.models import AccessFlow

logger = getLogger(__name__)

#: 协议维度的「任意」哨兵（protocol 字段的合法取值之一）
ANY = "any"

#: 地址维度的「任意」哨兵三段：0.0.0.0/0。与显式的 0.0.0.0/0 子网同键——语义本就
#: 相同，聚到一行是期望行为（见 AccessFlow 的 docstring）
ANY_ADDR: tuple[str, int, str] = ("0.0.0.0", 0, "")

#: 按 key 分块查已存在行时的块大小：OR 出上千个九元组会把 SQL 撑爆
_CHUNK = 500

#: 归一化后的地址三段：(ip, 前缀长度, 范围结束地址)
AddrPart = tuple[str, int, str]
#: 唯一键九元组：(源ip, 源前缀, 源范围尾, 目的ip, 目的前缀, 目的范围尾, 协议, 起始端口, 结束端口)
ComboKey = tuple[str, int, str, str, int, str, str, str, str]


# ---------------------------------------------------------------------------
# 归一化：唯一键的三个维度
# ---------------------------------------------------------------------------


def _canon_ip(value: Any) -> str | None:
    """IP 规范化：IPv6 大小写/压缩写法（``2001:DB8::1`` vs ``2001:db8::1``）必须落到同一个键。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def _host_part(ip: str) -> AddrPart:
    """单 IP → 三段（前缀长度按地址族取满：v4=32、v6=128）。"""
    return (ip, 32 if ipaddress.ip_address(ip).version == 4 else 128, "")


def _addr_parts(book) -> list[AddrPart]:
    """一条 AddressBook 记录 → 归一化后的地址三段列表（组会展开成多个成员）。"""
    kind = book.address_type
    if kind == "host":
        ip = _canon_ip(book.ip_address)
        return [_host_part(ip)] if ip else [ANY_ADDR]
    if kind == "subnet":
        if book.ip_address and book.ip_netmask is not None:
            try:
                network = ipaddress.ip_network(f"{book.ip_address}/{book.ip_netmask}", strict=False)
                return [(str(network.network_address), network.prefixlen, "")]
            except ValueError:
                pass
        ip = _canon_ip(book.ip_address)
        return [_host_part(ip)] if ip else [ANY_ADDR]
    if kind == "range":
        start, end = _canon_ip(book.ip_start), _canon_ip(book.ip_end)
        # range 没有前缀语义，prefix 固定 0；区分度靠 range_end 非空
        return [(start, 0, end)] if start and end else [ANY_ADDR]
    if kind == "addressbook":
        # 地址簿组：展开成成员条目。空组（PolicySaver 的占位记录、或解析还没填内容）
        # 按 any 处理——宁可保守地标成「任意」也不静默丢掉整条策略。
        parts: list[AddrPart] = []
        seen: set[AddrPart] = set()
        for child in book.children.all():
            for part in _addr_parts(child):
                if part not in seen:
                    seen.add(part)
                    parts.append(part)
        return parts or [ANY_ADDR]
    return [ANY_ADDR]


def _dim_parts(books: Iterable) -> list[AddrPart]:
    """一个地址维度（M2M 查询集）→ 去重后的三段列表；空维度回退 ``[ANY_ADDR]``。"""
    parts: list[AddrPart] = []
    seen: set[AddrPart] = set()
    for book in books:
        for part in _addr_parts(book):
            if part not in seen:
                seen.add(part)
                parts.append(part)
    return parts or [ANY_ADDR]


def _canon_port(value: Any) -> str:
    """端口归一：空即空串（非 NULL，参与唯一约束），纯数字去掉前导零（080 == 80）。"""
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() else text


def service_parts(service) -> tuple[str, str, str]:
    """一条 Service → ``(protocol, port, port2)``。

    protocol 取值与 ``Service.protocol`` 同一套（空值归 any）；port2 表示范围结束，
    与 port 相同或为空时归一成空串（``80-80`` 就是单端口）；icmp 等无端口的服务
    两段皆空。
    """
    protocol = str(service.protocol or "").strip().lower() or ANY
    port = _canon_port(service.port)
    port2 = _canon_port(service.port2)
    if port2 == port:
        port2 = ""
    return (protocol, port, port2)


# ---------------------------------------------------------------------------
# 展开
# ---------------------------------------------------------------------------


def _context_of(policy) -> dict[str, Any]:
    """一条策略 → 它在这行 contexts 里的载荷（设备信息冗余进来，查询时免 join）。"""
    return {
        "device_id": policy.device_id,
        "hostname": policy.device.hostname,
        "policy_pk": policy.pk,
        # Policy.policy_id 是设备内的策略编号（与 pk 不是一回事），两个都留
        "policy_id": policy.policy_id,
        "name": policy.name,
        "action": policy.action,
        "order": policy.order,
        "enabled": policy.enabled,
    }


def expand_policy(policy) -> list[dict]:
    """一条策略 → 笛卡尔积展开结果。

    每个组合带**单条**上下文（本策略的）；同批/跨批的重复组合由 ``upsert_flows``
    按 ``contexts`` 的键聚合。
    """
    sources = _dim_parts(policy.source_addresses.all())
    destinations = _dim_parts(policy.destination_addresses.all())
    services = list(dict.fromkeys(service_parts(s) for s in policy.services.all())) or [(ANY, "", "")]

    context_key = f"{policy.device_id}:{policy.pk}"
    context = _context_of(policy)
    return [
        {"key": (*source, *destination, *service), "contexts": {context_key: context}}
        for source, destination, service in product(sources, destinations, services)
    ]


def collect_device_flows(device) -> list[dict]:
    """一台设备的全部策略 → 按唯一键聚合后的展开结果（不含上下文摘除，那是入库的事）。"""
    from assets.models import AddressBook, Policy

    policies = (
        Policy.objects.filter(device=device)
        .select_related("device")
        .prefetch_related(
            # 组成员要随组一起取，否则 _addr_parts 里逐本书查 children 是 N+1
            Prefetch("source_addresses", queryset=AddressBook.objects.prefetch_related("children")),
            Prefetch("destination_addresses", queryset=AddressBook.objects.prefetch_related("children")),
            "services",
        )
        .order_by("order")
    )

    merged: dict[ComboKey, dict] = {}
    count = 0
    for policy in policies:
        count += 1
        for flow in expand_policy(policy):
            key: ComboKey = flow["key"]
            bucket = merged.setdefault(key, {"key": key, "contexts": {}})
            bucket["contexts"].update(flow["contexts"])
    logger.debug("设备 %s 展开 %s 条策略 → %s 个访问流", device.hostname, count, len(merged))
    return list(merged.values())


# ---------------------------------------------------------------------------
# 合并入库（先查后合并 + bulk；单写者前提）
# ---------------------------------------------------------------------------


def _row_key(row: AccessFlow) -> ComboKey:
    return (
        row.src_ip,
        row.src_prefix,
        row.src_range_end,
        row.dst_ip,
        row.dst_prefix,
        row.dst_range_end,
        row.protocol,
        row.port,
        row.port2,
    )


def _key_query(keys: list[ComboKey]) -> Q:
    query = Q()
    for key in keys:
        query |= Q(
            src_ip=key[0],
            src_prefix=key[1],
            src_range_end=key[2],
            dst_ip=key[3],
            dst_prefix=key[4],
            dst_range_end=key[5],
            protocol=key[6],
            port=key[7],
            port2=key[8],
        )
    return query


def _device_ids(contexts: dict) -> list[int]:
    return sorted({int(ctx["device_id"]) for ctx in contexts.values()})


def _policy_ids(contexts: dict) -> list[int]:
    return sorted({int(ctx["policy_pk"]) for ctx in contexts.values()})


def _touch(rows: list[AccessFlow]) -> None:
    """bulk_update 不走 pre_save，auto_now 的 updated_at 得自己填。"""
    now = timezone.now()
    for row in rows:
        row.updated_at = now
    AccessFlow.objects.bulk_update(rows, ["contexts", "device_ids", "policy_ids", "updated_at"], batch_size=500)


def upsert_flows(flows: Iterable[dict]) -> tuple[int, int]:
    """批量合并入库，返回 ``(新建行数, 变更行数)``。

    三步：同批按 key 聚合 → 分块查出已存在行（命中唯一约束索引）→ 内存合并
    contexts 后 bulk_create / bulk_update。contexts 没有实际变化的行不进 update。
    """
    merged: dict[ComboKey, dict] = {}
    for flow in flows:
        key: ComboKey = tuple(flow["key"])  # type: ignore[assignment]
        bucket = merged.setdefault(key, {"key": key, "contexts": {}})
        bucket["contexts"].update(flow["contexts"])
    if not merged:
        return (0, 0)

    existing: dict[ComboKey, AccessFlow] = {}
    keys = list(merged)
    for start in range(0, len(keys), _CHUNK):
        for row in AccessFlow.objects.filter(_key_query(keys[start : start + _CHUNK])):
            existing[_row_key(row)] = row

    to_create: list[AccessFlow] = []
    to_update: list[AccessFlow] = []
    for key, data in merged.items():
        row = existing.get(key)
        contexts = dict(data["contexts"])
        if row is None:
            to_create.append(
                AccessFlow(
                    src_ip=key[0],
                    src_prefix=key[1],
                    src_range_end=key[2],
                    dst_ip=key[3],
                    dst_prefix=key[4],
                    dst_range_end=key[5],
                    protocol=key[6],
                    port=key[7],
                    port2=key[8],
                    contexts=contexts,
                    device_ids=_device_ids(contexts),
                    policy_ids=_policy_ids(contexts),
                )
            )
            continue
        merged_contexts = {**row.contexts, **contexts}
        if merged_contexts == row.contexts:
            continue
        row.contexts = merged_contexts
        row.device_ids = _device_ids(merged_contexts)
        row.policy_ids = _policy_ids(merged_contexts)
        to_update.append(row)

    with transaction.atomic():
        if to_create:
            AccessFlow.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            _touch(to_update)
    return (len(to_create), len(to_update))


# ---------------------------------------------------------------------------
# 上下文摘除与整设备重建
# ---------------------------------------------------------------------------


def remove_device_context(device_id: int, keep_flow_keys: set[ComboKey] | None = None) -> int:
    """把一台设备从所有行的 contexts 里摘掉，返回受影响行数（行空了就整行删除）。

    策略变更/删除后旧 context 必须先清，否则「遗漏 / 多开」审计会残留过期数据。
    键前缀带冒号（``"1:"`` 不会误伤 ``"11:x"``）。

    ``keep_flow_keys`` 给了就保留**行键在其中**的该设备上下文——sync 语义（先合并
    当前状态、再摘残留）靠它做到真幂等：重放同一批时 upsert 与 remove 都是空操作。
    判据必须是**行键（九元组）**而不是 context 键：同一条策略的 context 会出现在它
    笛卡尔积的每一行上，策略换了地址后旧行与本批是同一个 (设备, 策略) 键、行却不同，
    按 context 键保留就漏摘了。``None`` 表示全摘。
    """
    prefix = f"{device_id}:"
    to_update: list[AccessFlow] = []
    to_delete: list[int] = []
    for row in AccessFlow.objects.filter(device_ids__contains=[device_id]):
        keep_row = keep_flow_keys is not None and _row_key(row) in keep_flow_keys
        kept = {key: ctx for key, ctx in row.contexts.items() if keep_row or not key.startswith(prefix)}
        if len(kept) == len(row.contexts):
            continue
        if kept:
            row.contexts = kept
            row.device_ids = _device_ids(kept)
            row.policy_ids = _policy_ids(kept)
            to_update.append(row)
        else:
            to_delete.append(row.pk)

    with transaction.atomic():
        if to_update:
            _touch(to_update)
        if to_delete:
            AccessFlow.objects.filter(pk__in=to_delete).delete()
    return len(to_update) + len(to_delete)


def sync_device(device_id: int, flows: list[dict]) -> tuple[int, int]:
    """把一台设备的访问流状态**同步**成 ``flows``：先合并写入，再摘除残留上下文。

    与「先删后建」的区别：重放同一批数据时两步都是空操作（真幂等，行 pk 不抖动，
    created 不虚高）；策略改了则是新键并入、旧键残留被摘掉。整段一个事务——中途
    失败不会留下「合了一半」的残局。设备没有策略时等价于清理。
    """
    keep_flow_keys = {tuple(flow["key"]) for flow in flows}
    with transaction.atomic():
        created, updated = upsert_flows(flows)
        remove_device_context(device_id, keep_flow_keys=keep_flow_keys)
    return (created, updated)


def rebuild_device(device) -> tuple[int, int]:
    """一台设备的完整重建（同步、进程内）：展开当前策略并同步进库。

    设备没有策略时等价于清理（把这台设备的残留上下文删干净）。
    """
    flows = collect_device_flows(device)
    created, updated = sync_device(device.pk, flows)
    logger.info("设备 %s AccessFlow 重建完成: 组合 %s，+%s ~%s", device.hostname, len(flows), created, updated)
    return (created, updated)
