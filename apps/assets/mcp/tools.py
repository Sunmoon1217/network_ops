"""资产域专属 MCP 工具（import 即注册）。

通用工具在 ``core.mcp.tools``（find / list_records / query / get_record / bundle /
relations）；本模块只放必须知道资产域业务语义的工具。当前只有 ``locate``：
它同时读登记（IPAddress）、观测（ArpMac）与台账（Device / Interface），再做三方
一致性判断——不是 ``filters`` 能表达的查询。
"""

from typing import Any

from django.db.models import Q
from django.utils import timezone
from mcp.server.mcpserver.exceptions import ToolError

import assets.mcp.specs  # noqa: F401 — import 即注册资产域实体
import core.mcp.tools  # noqa: F401 — 通用工具（find / list_records / query / ...）
from assets import models
from assets.mcp.specs import _mac_compact, _mac_variants
from core.mcp.server import mcp, with_db_lifecycle
from core.mcp.tools import _detect, _parse_ip

#: 观测数据超过这个时长没刷新就提示「旧数据」，避免拿三个月前的 ARP 下结论
STALE_HOURS = 24


@mcp.tool()
@with_db_lifecycle
def locate(target: str, limit: int = 20) -> dict[str, Any]:
    """定位一个 IP / MAC / 主机名「现在在哪」，并把登记与观测的冲突摆出来。

    回答的是三类数据的**一致性**，不是简单查表：

    - 登记（``IPAddress``）：这个地址规划给谁、状态是 used 还是 available
    - 观测（``ArpMac``）：哪些设备在哪个口看到过它——每台设备一份，同一地址可能多条
    - 台账（``Device.ip_address`` / ``Interface.ip_address``）：配置里写的是不是这个

    三者不一致才是最有价值的信息：登记为空却在线、同一地址对应多个 MAC、
    同一地址在多个端口被看到、ARP 表自己标记 conflict。

    参数：
    - target：IP（支持 IPv6）/ MAC（三种分隔符都认）/ 主机名。网段不行——那是
      ``find`` 或 ``list_records(entity_type="subnet")`` 的活
    - limit：观测条数上限，1~50

    返回：{target, kind, registry, observations, observed_total, devices, interfaces,
    conflicts, stale}。``registry`` 为 null 表示地址没登记；``stale=true`` 表示观测
    超过 24 小时没刷新，结论要打折。
    """
    text = (target or "").strip()
    if not text:
        raise ToolError("target 不能为空：可传 IP / MAC / 主机名")
    if not 1 <= limit <= 50:
        raise ToolError("limit 取 1~50")

    kind = _detect(text)
    if kind == "net":
        raise ToolError("locate 只接受单个地址 / MAC / 主机名；网段请用 find 或 list_records(entity_type='subnet')")

    ip = _parse_ip(text)
    mac = _mac_compact(text)

    registry: dict[str, Any] | None = None
    observations = models.ArpMac.objects.none()
    devices = models.Device.objects.none()
    interfaces = models.Interface.objects.none()

    if kind == "mac":
        cond = Q()
        for variant in _mac_variants(mac):
            cond |= Q(mac_address__iexact=variant)
        observations = models.ArpMac.objects.filter(cond).select_related("device").order_by("-updated_at")
    elif kind == "ip":
        hit = models.IPAddress.objects.filter(ip_address=ip).select_related("subnet", "device").first()
        if hit is not None:
            registry = {
                "ip_address": hit.ip_address,
                "status": hit.status,
                "status_display": hit.get_status_display(),
                "subnet": hit.subnet.network if hit.subnet else None,
                "device": hit.device.hostname if hit.device else None,
                "interface": hit.interface,
                "description": hit.description,
                "updated_at": hit.updated_at.isoformat(),
            }
        observations = models.ArpMac.objects.filter(ip_address=ip).select_related("device").order_by("-updated_at")
        devices = models.Device.objects.filter(ip_address=ip)
        interfaces = models.Interface.objects.filter(ip_address__icontains=ip)
    else:
        devices = models.Device.objects.filter(Q(hostname__icontains=text) | Q(remark__icontains=text))

    obs_rows = [
        {
            "device": item.device.hostname,
            "port": item.interface,
            "vlan": item.vlan,
            "ip": item.ip_address,
            "mac": item.mac_address,
            "arp_type": item.arp_type,
            "status": item.status,
            "learned_at": item.learned_at.isoformat() if item.learned_at else None,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in observations[:limit]
    ]

    conflicts: list[str] = []
    macs = {row["mac"].lower() for row in obs_rows}
    ports = {(row["device"], row["port"]) for row in obs_rows if row["port"]}
    observed_devices = {row["device"] for row in obs_rows}

    if registry is not None:
        if registry["status"] != "used" and obs_rows:
            conflicts.append(f"登记状态为「{registry['status_display']}」，但被 {len(observed_devices)} 台设备观测到在线")
        if registry["device"] and observed_devices and registry["device"] not in observed_devices:
            conflicts.append(f"登记设备是 {registry['device']}，但观测到的设备是 {', '.join(sorted(observed_devices))}")
    elif obs_rows:
        conflicts.append("地址在线但未在 IPAddress 中登记")
    if len(macs) > 1:
        conflicts.append(f"同一地址对应 {len(macs)} 个不同 MAC：{', '.join(sorted(macs))}")
    if len(ports) > 1:
        conflicts.append(f"同一地址在 {len(ports)} 个端口被观测到（VM 迁移、双上联或环路，需人工确认）")
    if any(row["status"] == "conflict" for row in obs_rows):
        conflicts.append("ARP 表自身把该条标记为 conflict")

    stale = False
    if obs_rows:
        newest = max(item.updated_at for item in observations[:limit])
        stale = (timezone.now() - newest).total_seconds() > STALE_HOURS * 3600

    return {
        "target": text,
        "kind": kind,
        "registry": registry,
        "observations": obs_rows,
        "observed_total": observations.count(),
        "devices": [{"id": item.pk, "hostname": item.hostname, "device_type": item.device_type, "ip_address": item.ip_address} for item in devices[:limit]],
        "interfaces": [
            {
                "device": item.device.hostname,
                "interface": item.interface,
                "ip_address": item.ip_address,
                "mode": item.mode,
            }
            for item in interfaces[:limit]
        ],
        "conflicts": conflicts,
        "stale": stale,
    }
