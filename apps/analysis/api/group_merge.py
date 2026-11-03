"""设备组配置合并的**公共层**（只读）。

同一个「设备组配置合并」能力在三个域被用到：

- **GTM / GSLB 集群**（``cluster`` 组）→ 配置展示页 + 互联网资产分析；
- **LTM / SLB 主备**（``ha`` / ``failover`` 组）→ 负载均衡页 + 路径追踪；
- **防火墙主备**（``ha`` / ``failover`` 组）→ 防火墙页 + 路径追踪。

三者的**组口径与合并信封**一致，差异只在「同一份配置怎么识别为同一条」与「冲突字段怎么取
值」，所以把可复用的部分收到这里，各域只写自己的策略：

- 组划分：哪些设备算一组（``group_types``）、一台设备多组时取哪个、未入组设备各自成组；
- 合并信封：每个合并条目都带 ``device``（出现它的设备主机名逗号拼接）/
  ``inconsistent``（同名条目取值不同）/ ``conflict_fields``（不一致的字段名）；
- 取值工具：``_differs``（多值比较）/ ``_union_lists``（列表并集去重）。

**不建模型存合并结果**：合并是「读时算」的廉价内存 join（每组若干次查询 + dict 组装）。
组配置入库是低频动作、且随时可能被重新解析覆盖（更新既有 ``DeviceConfig`` 还不触发流水线），
存派生表只会背上失效同步的包袱。资产分析要落库的是**自己的结果缓存**，不是这份合并中间态。

用法：``resolve_groups("gslb", {"cluster"})`` / ``resolve_groups("slb", HA_GROUP_TYPES)`` /
``resolve_groups("firewall", HA_GROUP_TYPES)``，拿到 ``GroupKey`` 列表后各域自己组装合并行。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from assets.models import Device, DeviceGroup

# 参与「主备合并」的组类型：ha（主备）与 failover（故障接管）是同一类语义（一个主一个备），
# 单机（single）与堆叠（stack）**不参与合并**——堆叠组备机没有配置、配置归属主设备
# （见 ingest.config_owner），不需要在这里并。集群（cluster）只有 GSLB 用，单独传入。
HA_GROUP_TYPES = frozenset({"ha", "failover"})


@dataclass
class GroupKey:
    """一个设备组的可复用信封：键 + 名字 + 成员设备（按 hostname 排序）。

    ``key`` 的形状与 GSLB 集群一致（``group-<id>`` / ``device-<id>``），保证「一台未入组
    设备」也是一个可引用的单机组，前端下拉与过滤都用同一个键形状。
    """

    key: str  # "group-<id>" / "device-<id>"
    name: str  # 组名 / 单机设备 hostname
    group_id: int | None
    devices: list[Device]


def resolve_groups(
    device_type: str,
    group_types: frozenset[str],
    device_id: int | None = None,
    group_key: str | None = None,
) -> list[GroupKey]:
    """把某类型的设备划分成合并组；``device_id`` / ``group_key`` 用于收窄范围。

    - 设备只在 ``group_types`` 命中的组里成团；同组多台设备即一个合并组；
    - 一台设备出现在多个命中组时，按（组名, id）排序取第一个（否则它会同时出现在
      两个组里、行数与 device 拼接都不稳定）；
    - 未入组的该类型设备各自成为单机组（名字取 hostname）。
    """
    devices = {device.pk: device for device in Device.objects.filter(device_type=device_type)}
    groups: dict[str, GroupKey] = {}
    assigned: set[int] = set()

    group_qs = DeviceGroup.objects.filter(group_type__in=group_types).prefetch_related("members__device")
    for group in group_qs.order_by("name", "id"):
        members = sorted(
            (m.device for m in group.members.all() if m.device_id in devices and m.device_id not in assigned),
            key=lambda device: device.hostname,
        )
        if not members:
            continue
        for device in members:
            assigned.add(device.pk)
        groups[f"group-{group.pk}"] = GroupKey(
            key=f"group-{group.pk}", name=group.name, group_id=group.pk, devices=members
        )

    for device in sorted(devices.values(), key=lambda item: item.hostname):
        if device.pk not in assigned:
            groups[f"device-{device.pk}"] = GroupKey(
                key=f"device-{device.pk}", name=device.hostname, group_id=None, devices=[device]
            )

    resolved = sorted(groups.values(), key=lambda group: (group.name, group.key))
    if group_key:
        # 同时认组键（group-3 / device-7）与组名——前端下拉用键，人工调接口写组名更顺手
        return [group for group in resolved if group.key == group_key or group.name == group_key]
    if device_id is not None:
        return [group for group in resolved if any(device.pk == device_id for device in group.devices)]
    return resolved


# ---------------------------------------------------------------------------
# 合并信封工具（各域合并策略共用）
# ---------------------------------------------------------------------------


def _differs(values) -> bool:
    """一组取值是否不一致：None / 空串 / 数字 / 列表都能比较（JSON 归一后去重）。"""
    seen = {json.dumps(value, sort_keys=True, default=str) for value in values}
    return len(seen) > 1


def _union_lists(values) -> list:
    """多个列表按序并集去重（monitor 这类列表字段用）。"""
    union: list = []
    for items in values:
        for item in items or []:
            if item not in union:
                union.append(item)
    return union


def _join_devices(device_ids, hostname: dict[int, str]) -> str:
    """把一组设备 id 拼成 hostname 逗号串（按 id 顺序——调用方已按 hostname 排好序）。"""
    return ",".join(hostname[device_id] for device_id in device_ids)
