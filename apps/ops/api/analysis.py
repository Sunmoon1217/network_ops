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

**结果不实时计算**：分析成本不低而结果变化不频繁，所以只在手动触发
``POST /api/internet-analysis/analyze/`` 时重算并写入 ``InternetAnalysis`` 缓存表；
``GET /api/internet-analysis/`` 与导出接口都只读缓存。
"""

import ipaddress
import time
from io import BytesIO
from typing import cast
from urllib.parse import quote

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from assets.models import Device, GtmPool, GtmVServer, GtmWideip, LtmPool, LtmPoolMember, LtmVirtualServer
from ops.models import InternetAnalysis

# 级联展开层数上限，防止 LTM 之间互相指向造成死循环
MAX_NESTED_DEPTH = 3

# 扁平表格的列：一行就是一条从域名到最终后端的完整链路
#
# 只保留 LLB / SLB 两级虚拟服务器与最后一跳的服务器：
# **LLB 的池成员就是 SLB 的虚拟服务器**（同一份地址:端口），占两组列是重复的，
# 所以合并成 LLB_VS / SLB_VS / 服务器 三段。字段来源见每列注释。
EXPORT_HEADERS = [
    "域名",  # GtmWideip.name
    "LLB_VS地址#端口",  # LtmVirtualServer.vs_address#vs_port
    "LLB_Rule规则",  # LtmVirtualServer.rules
    "SLB_VS地址#端口",  # 级联下一级的 LtmVirtualServer.vs_address#vs_port
    "SLB_Rule规则",  # 级联下一级的 LtmVirtualServer.rules
    "服务器地址#端口",  # 链路最后一跳的池成员地址#端口
    "负责人",  # ServerOwner.owner，按服务器地址反查
]
EXPORT_COLUMN_WIDTHS = (28, 26, 30, 26, 30, 26, 16)


def _parse_member_entry(entry) -> tuple[str, str, dict]:
    """把 GTM 池成员条目规范化为 (server_name, vs_name, 原始信息)。

    要兼容三种形态：
    - 模板解析产出：``{"server_name": ..., "vs_name": ...}``
    - **GtmPoolSaver 入库后的口径**：``{"server": ..., "vserver": ...}``
      （``_normalize_members`` 会把 key 改名，这里必须认，否则 vs_name 恒为空，
      链路在第一步就被判成「GTM 虚拟服务器未找到」）
    - 手工录入的 ``"server:vs"`` 字符串
    """
    if isinstance(entry, dict):
        server_name = str(entry.get("server_name") or entry.get("server") or "")
        vs_name = str(entry.get("vs_name") or entry.get("vserver") or entry.get("virtual_server") or "")
        # 缺哪一半就用 "server:vs" 形式的 name 补哪一半
        if not server_name or not vs_name:
            left, _, right = str(entry.get("name") or "").partition(":")
            server_name = server_name or left
            vs_name = vs_name or right
        return server_name, vs_name, entry
    raw = str(entry or "")
    server_name, _, vs_name = raw.partition(":")
    return server_name, vs_name, {}


def _normalize_ip(value) -> str:
    """把地址规范化为可比较形式：IPv6 统一小写压缩，非法值退化为小写文本。

    两边字段类型不同：``GtmVServer.ip_address`` 是 GenericIPAddressField，Django 会
    规范化（小写 + 压缩）；而 ``LtmVirtualServer.vs_address`` 是 CharField，原样存。
    直接按字符串比较时，``2001:DB8::1`` / ``2001:0db8::1`` / 展开写法都匹配不上
    同一个地址，IPv6 的链路就会断在"找不到对应的 LLB 虚拟服务器"。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text.lower()


# 地址与端口之间的分隔符。
#
# **不要用 ":"**：IPv6 地址本身就带冒号，``2001:db8::1:80`` 分不清哪一段是端口
# （回退写法 ``[...]:80`` 虽然标准，但 IPv4 用方括号又显得多余）。
# 用 "#"：它不可能出现在 IPv4/IPv6 里，含义唯一且紧凑。
# 前端 internet-asset.vue 里的 TARGET_SEPARATOR 要与这里保持一致。
TARGET_SEPARATOR = "#"


def _join_ip_port(ip: str | None, port: str | None) -> str:
    """拼成 "地址#端口"，端口缺失时只返回地址"""
    if not ip:
        return ""
    return f"{ip}{TARGET_SEPARATOR}{port}" if port else str(ip)


class _AssetIndex:
    """一次分析内复用的内存索引，避免逐条查库"""

    def __init__(self) -> None:
        self.vservers: dict[tuple[str, str], GtmVServer] = {}
        for vserver in GtmVServer.objects.select_related("server").all():
            self.vservers.setdefault((vserver.server.name, vserver.name), vserver)

        self.ltm_virtuals: dict[tuple[str, str], list[LtmVirtualServer]] = {}
        for virtual in LtmVirtualServer.objects.select_related("device").all():
            key = (_normalize_ip(virtual.vs_address), str(virtual.vs_port or ""))
            self.ltm_virtuals.setdefault(key, []).append(virtual)

        # 池与成员都按「设备 + 池名」索引：不同设备上可以有同名池，
        # 只按 pool_name 索引会把它们的成员混到一起
        self.ltm_pool_members: dict[tuple[int, str], list[LtmPoolMember]] = {}
        for member in LtmPoolMember.objects.all():
            self.ltm_pool_members.setdefault((member.device_id, member.pool_name), []).append(member)

        self.ltm_pools: set[tuple[int, str]] = set(LtmPool.objects.values_list("device_id", "name"))

    def find_vserver(self, server_name: str, vs_name: str) -> GtmVServer | None:
        return self.vservers.get((server_name, vs_name))

    def find_ltm_virtual(self, ip: str | None, port: str | None) -> LtmVirtualServer | None:
        """按 IP:端口 找 LTM 虚拟服务器（同名时取 pk 最小的一条）"""
        if not ip:
            return None
        normalized = _normalize_ip(ip)
        candidates = self.ltm_virtuals.get((normalized, str(port or "")), [])
        if not candidates and port:
            # 端口为空或写法不一致时，退化为只按地址匹配
            candidates = [v for (addr, _), items in self.ltm_virtuals.items() if addr == normalized for v in items]
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
        "pool_found": bool(virtual.pool) and (virtual.device_id, virtual.pool) in index.ltm_pools,
        "rules": [str(rule) for rule in (virtual.rules or [])],
        "members": [],
    }

    if not virtual.pool:
        return node

    for member in index.ltm_pool_members.get((virtual.device_id, virtual.pool), []):
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


def _resolve_device(request):
    """从 query 参数取出设备，返回 ``(device, error_response)``"""
    device_id = request.query_params.get("device")
    if not device_id:
        return None, Response({"error": "device 参数必填"}, status=http_status.HTTP_400_BAD_REQUEST)

    device = Device.objects.filter(pk=device_id).first()
    if not device:
        return None, Response({"error": "设备不存在"}, status=http_status.HTTP_404_NOT_FOUND)
    return device, None


def _cached_response(cached: InternetAnalysis) -> dict:
    """把缓存记录拼成响应体：分析结果 + 负责人映射 + 分析时间与耗时

    ``owners`` 每次现查：负责人是人工维护的，改了不该要求重跑分析才能看到。
    """
    result = cached.result or {}
    return {
        **result,
        "owners": build_owner_map(result),
        "analyzed_at": cached.analyzed_at,
        "duration_ms": cached.duration_ms,
    }


def _get_cached_or_404(device):
    """取该设备的分析缓存，没有则返回 404 响应"""
    cached = InternetAnalysis.objects.filter(device=device).first()
    if cached:
        return cached, None
    return None, Response(
        {"error": "该设备尚未分析", "device": device.pk, "analyzed_at": None},
        status=http_status.HTTP_404_NOT_FOUND,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def internet_analysis(request):
    """读取缓存的分析结果: GET /api/internet-analysis/?device=<id>

    这里不触发分析——分析要遍历 GTM/LTM 多张表并在内存里做关联，只在手动
    调用 analyze 接口时执行；平时查询直接返回上一次的结果。
    """
    device, error = _resolve_device(request)
    if error:
        return error

    cached, error = _get_cached_or_404(device)
    if error:
        return error
    return Response(_cached_response(cast(InternetAnalysis, cached)))


@api_view(["POST"])
@permission_classes([AllowAny])
def internet_analysis_run(request):
    """立即分析并刷新缓存: POST /api/internet-analysis/analyze/?device=<id>"""
    device, error = _resolve_device(request)
    if error:
        return error

    started = time.monotonic()
    result = analyze_device(cast(Device, device))
    duration_ms = int((time.monotonic() - started) * 1000)

    cached, _ = InternetAnalysis.objects.update_or_create(
        device=device,
        defaults={"result": result, "duration_ms": duration_ms},
    )
    return Response(_cached_response(cached))


# ---------------------------------------------------------------------------
# 扁平化：一行 = 一条从 WideIP 到最终后端的完整链路
# ---------------------------------------------------------------------------


def _member_sort_key(member: dict) -> tuple[int, int]:
    """池成员按 order 排序，没有 order 的排最后"""
    order = member.get("order")
    return (0, order) if isinstance(order, int) else (1, 0)


def _note(*parts) -> str:
    return " · ".join(str(part) for part in parts if part)


def _walk_ltm_paths(node: dict, prefix: list[tuple[dict, dict | None]]) -> list[list[tuple[dict, dict | None]]]:
    """沿 LTM 子树走到叶子，返回所有路径。

    每条路径逐级记录 ``(虚拟服务器节点, 指向下一级的池成员)``，调用方就能按级取字段
    （第 0 级 = LLB，第 1 级 = SLB）。某级没有成员时该虚拟服务器自己就是终点，
    成员为 ``None``。
    """
    members = node.get("members") or []
    if not members:
        return [[*prefix, (node, None)]]

    paths: list[list[tuple[dict, dict | None]]] = []
    for member in members:
        step = (node, member)
        if member.get("nested"):
            paths.extend(_walk_ltm_paths(member["nested"], [*prefix, step]))
        else:
            paths.append([*prefix, step])
    return paths


def _ltm_rules(path: list[tuple[dict, dict | None]], index: int) -> str:
    """取路径第 index 级虚拟服务器的 iRules，多条用逗号连接"""
    if index >= len(path):
        return ""
    node, _ = path[index]
    return ", ".join(str(rule) for rule in (node.get("rules") or []))


def _final_target(row: dict) -> tuple[str, str]:
    """链路最后一跳的 (地址, 端口)。

    两级链路取 SLB 的池成员，一级链路取 LLB 的池成员；链路中断（没有对应的 LTM
    虚拟服务器）时回退到 GTM 虚拟服务器——那种情况下它的地址就是最终地址。
    """
    for address_key, port_key in (
        ("slb_member_address", "slb_member_port"),
        ("llb_member_address", "llb_member_port"),
        ("gtm_ip", "gtm_port"),
    ):
        address = row.get(address_key) or ""
        if address:
            return str(address), str(row.get(port_key) or "")
    return "", ""


def _final_ip(row: dict) -> str:
    """只取链路最后的 IP，用于反查负责人"""
    return _final_target(row)[0]


def _load_owner_index() -> dict[str, str]:
    """规范化 IP -> 负责人。

    只取启用的记录；两边都过 ``_normalize_ip``，否则 ``2001:DB8::1`` 这类写法
    与实际入库的压缩形式对不上。
    """
    from assets.models import ServerOwner

    return {_normalize_ip(item.ip): item.owner for item in ServerOwner.objects.filter(status="enabled") if item.owner}


def _ltm_columns(path: list[tuple[dict, dict | None]], index: int) -> tuple[str, str, str, str]:
    """取路径第 index 级的 (虚拟服务器地址, 端口, 池成员地址, 池成员端口)"""
    if index >= len(path):
        return ("", "", "", "")
    node, member = path[index]
    if member is None:
        # 该级没有池成员，虚拟服务器自己就是终点
        return (str(node.get("vs_address") or ""), str(node.get("vs_port") or ""), "", "")
    return (
        str(node.get("vs_address") or ""),
        str(node.get("vs_port") or ""),
        str(member.get("address") or ""),
        str(member.get("port") or ""),
    )


def _blank_row(wideip: dict) -> dict:
    return {
        "wideip": wideip.get("name") or "",
        "rtype": wideip.get("rtype") or "",
        "gtm_ip": "",
        "gtm_port": "",
        "llb_address": "",
        "llb_port": "",
        "llb_rules": "",
        "llb_member_address": "",
        "llb_member_port": "",
        "slb_address": "",
        "slb_port": "",
        "slb_rules": "",
        "slb_member_address": "",
        "slb_member_port": "",
        "owner": "",
        "note": "",
    }


def _member_path_rows(wideip: dict, member: dict) -> list[dict]:
    """单个 GTM 池成员展开成 1..N 行（LTM 分叉时一条成员对应多行）"""
    status = member.get("status") or ""

    def _base() -> dict:
        row = _blank_row(wideip)
        vserver = member.get("vserver")
        if vserver:
            row["gtm_ip"] = str(vserver.get("ip_address") or "")
            row["gtm_port"] = str(vserver.get("port") or "")
        return row

    # ① GTM 虚拟服务器缺失：链路在此中断
    if status == "vserver_not_found":
        row = _base()
        row["note"] = "GTM 虚拟服务器未找到"
        return [row]

    # ② 无对应 LTM 虚拟服务器：GTM VS 的地址即最终地址，LTM 两段留空
    if status == "ltm_not_found":
        row = _base()
        row["note"] = _note("无对应 LTM 虚拟服务器", "GTM 虚拟服务器地址即最终地址")
        return [row]

    # ③ 解析成功：LTM 子树的每条路径各占一行
    ltm = member.get("ltm")
    paths = _walk_ltm_paths(ltm, []) if ltm else []
    if not paths:
        return [_base()]

    rows: list[dict] = []
    for path in paths:
        row = _base()
        (row["llb_address"], row["llb_port"], row["llb_member_address"], row["llb_member_port"]) = _ltm_columns(path, 0)
        (row["slb_address"], row["slb_port"], row["slb_member_address"], row["slb_member_port"]) = _ltm_columns(path, 1)
        row["llb_rules"] = _ltm_rules(path, 0)
        row["slb_rules"] = _ltm_rules(path, 1)
        notes = []
        if len(path) < 2:
            notes.append("仅一级 LTM")
        elif len(path) > 2:
            # 表格只留两级，更深的级联在这里说明，避免信息凭空消失
            notes.append(f"还有 {len(path) - 2} 层级联未展开")
        row["note"] = _note(*notes)
        rows.append(row)
    return rows


def build_path_rows(result: dict, owner_index: dict[str, str] | None = None) -> list[dict]:
    """把 analyze_device 的结果扁平化成「一行一条链路」的表格行。

    列固定为 GTM 四列 + LTM 两级（LLB / SLB）各 5 列 + 负责人 + 说明。

    负责人按链路最后的 IP 反查 ``ServerOwner``。这里不把它写进分析缓存，而是在
    出表时现查：改了负责人不必重跑分析就能立刻反映到页面与导出。``owner_index``
    可注入，便于测试。
    """
    if owner_index is None:
        owner_index = _load_owner_index()

    rows: list[dict] = []

    for wideip in result.get("wideips", []):
        for pool in wideip.get("pools", []):
            members = sorted(pool.get("members") or [], key=_member_sort_key)
            if not members:
                # 池没有成员时也保留一行，避免这条记录从表里凭空消失
                row = _blank_row(wideip)
                row["note"] = "该池没有成员" if pool.get("found") else "池未找到"
                rows.append(row)
                continue

            for member in members:
                rows.extend(_member_path_rows(wideip, member))

    for row in rows:
        # final_ip 只用于反查负责人（以及给前端做同一份映射），不进导出列
        row["final_ip"] = _final_ip(row)
        row["owner"] = owner_index.get(_normalize_ip(row["final_ip"]), "")

    return rows


def build_owner_map(result: dict) -> dict[str, str]:
    """链路最后的 IP（原始写法）-> 负责人。

    前端表格自己扁平化分析结果，拿不到数据库；这里把现查的负责人按**原始 IP 字符串**
    返回，前端就能用同一份回退规则直接查表，不必在 JS 里实现 IPv6 规范化。
    """
    return {
        row["final_ip"]: row["owner"] for row in build_path_rows(result) if row.get("final_ip") and row.get("owner")
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def internet_analysis_export(request):
    """导出缓存的分析结果为 xlsx: GET /api/internet-analysis/export/?device=<id>

    与查询接口一致，只读缓存；没分析过就提示先执行分析，不在这里顺手算一遍。
    """
    device, error = _resolve_device(request)
    if error:
        return error
    device = cast(Device, device)

    cached, error = _get_cached_or_404(device)
    if error:
        return error
    cached = cast(InternetAnalysis, cached)
    rows = build_path_rows(cached.result or {})

    workbook = Workbook()
    sheet = workbook.active
    if sheet is None:
        sheet = workbook.create_sheet()
    sheet.title = "互联网资产分析"
    sheet.append(EXPORT_HEADERS)
    for row in rows:
        sheet.append(
            [
                row["wideip"],
                _join_ip_port(row["llb_address"], row["llb_port"]),
                row["llb_rules"],
                _join_ip_port(row["slb_address"], row["slb_port"]),
                row["slb_rules"],
                _join_ip_port(*_final_target(row)),
                row["owner"],
            ]
        )
    # 列宽跟着表头走：写死 "ABCDEFGHIJKLM" 在加列时会静默少设宽度
    for index, width in enumerate(EXPORT_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    buffer = BytesIO()
    workbook.save(buffer)

    filename = f"internet-asset-{device.hostname}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response
