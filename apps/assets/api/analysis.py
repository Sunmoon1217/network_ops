"""互联网资产分析。

从 GSLB 设备的 WideIP 出发，逐层解析到最终的后端地址：

    GSLB 设备
      └─ GtmWideip（域名，pools 为池名列表）
          └─ GtmPool（池，members 形如 "server_name:vs_name"）
              └─ GtmVServer（GTM 侧虚拟服务器，含 IP 与端口）
                  ├─ 未找到 → 结果标记「未找到」
                  └─ 找到 → 用 IP:端口 查 LtmVirtualServer
                      ├─ 未找到 → 返回 vserver 的 IP:端口
                      └─ 找到 → LtmPool → LtmPoolMember
                          └─ 用成员的 IP:端口 再查 LtmVirtualServer（级联 LB）
                              └─ 找到 → 返回该成员的 IP:端口

整个过程只做 4 次查询（WideIP / GTM VServer / LTM VS / LTM 成员各一次），
再在内存里索引匹配，避免逐条记录查库。
"""

from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from assets.models import Device, GtmPool, GtmVServer, GtmWideip, LtmPool, LtmPoolMember, LtmVirtualServer

# 级联展开层数上限，防止 LTM 之间互相指向造成死循环
MAX_NESTED_DEPTH = 3


def _parse_member_entry(entry) -> tuple[str, str, dict]:
    """把 GTM 池成员条目规范化为 (server_name, vs_name, 原始信息)。

    模板解析出的形态是 {"server_name": ..., "vs_name": ..., ...}；
    同时兼容手工录入的 "server:vs" 字符串。
    """
    if isinstance(entry, dict):
        server_name = str(entry.get("server_name") or entry.get("server") or "")
        vs_name = str(entry.get("vs_name") or entry.get("virtual_server") or "")
        if not server_name and not vs_name:
            raw = str(entry.get("name") or "")
            server_name, _, vs_name = raw.partition(":")
        return server_name, vs_name, entry
    raw = str(entry or "")
    server_name, _, vs_name = raw.partition(":")
    return server_name, vs_name, {}


def _join_ip_port(ip: str | None, port: str | None) -> str:
    """拼成 "ip:port"，端口缺失时只返回 IP"""
    if not ip:
        return ""
    return f"{ip}:{port}" if port else str(ip)


class _AssetIndex:
    """一次分析内复用的内存索引，避免逐条查库"""

    def __init__(self) -> None:
        self.vservers: dict[tuple[str, str], GtmVServer] = {}
        for vserver in GtmVServer.objects.select_related("server").all():
            self.vservers.setdefault((vserver.server.name, vserver.name), vserver)

        self.ltm_virtuals: dict[tuple[str, str], list[LtmVirtualServer]] = {}
        for virtual in LtmVirtualServer.objects.select_related("device").all():
            key = (virtual.vs_address or "", str(virtual.vs_port or ""))
            self.ltm_virtuals.setdefault(key, []).append(virtual)

        self.ltm_pool_members: dict[str, list[LtmPoolMember]] = {}
        for member in LtmPoolMember.objects.all():
            self.ltm_pool_members.setdefault(member.pool_name, []).append(member)

        self.ltm_pools: set[str] = set(LtmPool.objects.values_list("name", flat=True))

    def find_vserver(self, server_name: str, vs_name: str) -> GtmVServer | None:
        return self.vservers.get((server_name, vs_name))

    def find_ltm_virtual(self, ip: str | None, port: str | None) -> LtmVirtualServer | None:
        """按 IP:端口 找 LTM 虚拟服务器（同名时取 pk 最小的一条）"""
        if not ip:
            return None
        candidates = self.ltm_virtuals.get((ip, str(port or "")), [])
        if not candidates and port:
            # 端口为空或写法不一致时，退化为只按地址匹配
            candidates = [v for (addr, _), items in self.ltm_virtuals.items() if addr == ip for v in items]
        if not candidates:
            return None
        return sorted(candidates, key=lambda v: v.pk)[0]


def _expand_ltm_virtual(virtual: LtmVirtualServer, index: _AssetIndex, depth: int) -> dict:
    """展开 LTM 虚拟服务器 → 池 → 成员，成员继续级联查下层虚拟服务器"""
    node: dict = {
        "device": virtual.device.hostname,
        "name": virtual.name,
        "vs_address": virtual.vs_address,
        "vs_port": virtual.vs_port or "",
        "status": virtual.status,
        "pool": virtual.pool or "",
        "pool_found": bool(virtual.pool) and virtual.pool in index.ltm_pools,
        "members": [],
    }

    if not virtual.pool:
        return node

    for member in index.ltm_pool_members.get(virtual.pool, []):
        member_node: dict = {
            "name": member.name,
            "address": member.address or "",
            "port": member.port or "",
            "ip_port": _join_ip_port(member.address, member.port),
            "nested": None,
            "matched_ip_port": "",
        }
        if depth > 0 and member.address:
            nested = index.find_ltm_virtual(member.address, member.port)
            if nested:
                # 找到下层虚拟服务器 → 按需求返回该成员自身的 IP:端口
                member_node["nested"] = _expand_ltm_virtual(nested, index, depth - 1)
                member_node["matched_ip_port"] = member_node["ip_port"]
        node["members"].append(member_node)

    return node


def analyze_device(device: Device) -> dict:
    """解析指定 GSLB 设备上所有 WideIP 的互联网资产链路"""
    index = _AssetIndex()
    result: dict = {
        "device": {"id": device.pk, "hostname": device.hostname, "device_type": device.device_type},
        "wideips": [],
    }

    pools_by_name = {pool.name: pool for pool in GtmPool.objects.filter(device=device)}

    for wideip in GtmWideip.objects.filter(device=device).order_by("name"):
        wideip_node: dict = {
            "id": wideip.pk,
            "name": wideip.name,
            "rtype": wideip.rtype,
            "lb_mode": wideip.lb_mode,
            "pool_count": len(wideip.pools or []),
            "pools": [],
        }

        for pool_name in wideip.pools or []:
            pool_node: dict = {"name": str(pool_name), "found": False, "lb_mode": "", "members": []}
            pool = pools_by_name.get(str(pool_name))
            if pool:
                pool_node["found"] = True
                pool_node["lb_mode"] = pool.lb_mode
                for entry in pool.members or []:
                    server_name, vs_name, raw = _parse_member_entry(entry)
                    member_node: dict = {
                        "server_name": server_name,
                        "vs_name": vs_name,
                        "member_ref": f"{server_name}:{vs_name}" if (server_name or vs_name) else "",
                        "state": raw.get("member_status", "") if isinstance(raw, dict) else "",
                        "order": raw.get("member_order") if isinstance(raw, dict) else None,
                        "status": "",
                        "message": "",
                        "vserver": None,
                        "ltm": None,
                        "fallback_ip_port": "",
                    }

                    vserver = index.find_vserver(server_name, vs_name)
                    if not vserver:
                        # 第一步：没找到 GTM 虚拟服务器
                        member_node["status"] = "vserver_not_found"
                        member_node["message"] = "未找到"
                        pool_node["members"].append(member_node)
                        continue

                    member_node["vserver"] = {
                        "id": vserver.pk,
                        "name": vserver.name,
                        "server_name": vserver.server.name,
                        "ip_address": vserver.ip_address or "",
                        "port": vserver.port or "",
                        "monitor": vserver.monitor or "",
                    }

                    # 第二步：用 vserver 的 IP:端口 找 LTM 虚拟服务器
                    virtual = index.find_ltm_virtual(vserver.ip_address, vserver.port)
                    if not virtual:
                        member_node["status"] = "ltm_not_found"
                        member_node["message"] = "未匹配到 LTM 虚拟服务器"
                        member_node["fallback_ip_port"] = _join_ip_port(vserver.ip_address, vserver.port)
                        pool_node["members"].append(member_node)
                        continue

                    # 第三步：展开 LTM 池与成员，并对成员继续级联
                    member_node["status"] = "resolved"
                    member_node["ltm"] = _expand_ltm_virtual(virtual, index, MAX_NESTED_DEPTH - 1)
                    pool_node["members"].append(member_node)

            wideip_node["pools"].append(pool_node)

        result["wideips"].append(wideip_node)

    return result


@api_view(["GET"])
@permission_classes([AllowAny])
def internet_analysis(request):
    """互联网资产分析: GET /api/assets/internet-analysis/?device=<id>"""
    device_id = request.query_params.get("device")
    if not device_id:
        return Response({"error": "device 参数必填"}, status=http_status.HTTP_400_BAD_REQUEST)

    device = Device.objects.filter(pk=device_id).first()
    if not device:
        return Response({"error": "设备不存在"}, status=http_status.HTTP_404_NOT_FOUND)

    return Response(analyze_device(device))
