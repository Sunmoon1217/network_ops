"""
路径追踪算法

模拟数据包从源到目的的转发过程：
1. 整理源目地址端口
2. 查找源目地址所在VRF，如果是同一个VRF，直接返回
3. 循环：
   a. 如果当前设备是LB，检查VS匹配
   b. 如果当前设备是FW，策略匹配
   c. 查找路由，找不到则结束
   d. 如果是直连路由，结束
   e. 否则更新VRF为下一跳VRF
"""

import ipaddress
from dataclasses import dataclass, field

from assets.models import (
    AddressBook,
    Device,
    Interface,
    LtmPoolMember,
    LtmVirtualServer,
    NatRule,
    Policy,
    Route,
    Service,
    Subnet,
    Vrf,
)

MAX_HOPS = 50
MAX_ADDRESSBOOK_RECURSION = 10


@dataclass
class HopResult:
    device_name: str
    device_id: int
    device_type: str
    zone: str
    vrf: str = "default"
    matched_policy: dict | None = None
    matched_nat: dict | None = None
    matched_route: dict | None = None
    matched_vs: dict | None = None
    action: str = "allow"
    src_before: str = ""
    src_after: str = ""
    dst_before: str = ""
    dst_after: str = ""
    port_before: str = ""
    port_after: str = ""


@dataclass
class TraceResult:
    hops: list[HopResult] = field(default_factory=list)
    final_src: str = ""
    final_dst: str = ""
    final_port: str = ""
    blocked: bool = False
    blocked_by: str = ""
    lb_backend: list[dict] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _ip_in_addressbook(ip_str: str, ab: AddressBook, _visited: set[int] | None = None, _depth: int = 0) -> bool:
    """判断IP是否在地址簿中"""
    if _visited is None:
        _visited = set()
    if _depth > MAX_ADDRESSBOOK_RECURSION or ab.pk in _visited:
        return False
    _visited.add(ab.pk)

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if ab.address_type == "host" and ab.ip_address:
        return ip == ipaddress.ip_address(ab.ip_address)
    elif ab.address_type == "subnet" and ab.ip_address and ab.ip_netmask:
        network = ipaddress.ip_network(f"{ab.ip_address}/{ab.ip_netmask}", strict=False)
        return ip in network
    elif ab.address_type == "range" and ab.ip_start and ab.ip_end:
        return int(ipaddress.ip_address(ab.ip_start)) <= int(ip) <= int(ipaddress.ip_address(ab.ip_end))
    elif ab.address_type == "addressbook":
        return any(_ip_in_addressbook(ip_str, child, _visited, _depth + 1) for child in ab.children.all())
    return False


def _match_address_list(ip_str: str, address_book) -> bool:
    """匹配地址列表"""
    return any(_ip_in_addressbook(ip_str, ab) for ab in address_book.all())


def _match_service(port_str: str, services) -> bool:
    """匹配服务端口"""
    if not port_str:
        return False
    for svc in services.all():
        port_range = svc.port or svc.port2
        if svc.port and svc.port2:
            port_range = f"{svc.port}-{svc.port2}"
        if not port_range:
            continue
        for part in port_range.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                if int(start) <= int(port_str) <= int(end):
                    return True
            elif int(port_str) == int(part):
                return True
    return False


def _subnet_cache() -> list:
    """加载所有子网（同一请求内缓存）"""
    if not hasattr(_subnet_cache, "_data"):
        setattr(_subnet_cache, "_data", list(Subnet.objects.all()))
        return getattr(_subnet_cache, "_data")
    else:
        return getattr(_subnet_cache, "_data")


def _clear_subnet_cache():
    """清除子网缓存（测试用）"""
    if hasattr(_subnet_cache, "_data"):
        delattr(_subnet_cache, "_data")


def _find_subnet_for_ip(ip_str: str) -> Subnet | None:
    """查找IP所属子网"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None

    best_match, best_prefix = None, -1
    for subnet in _subnet_cache():
        try:
            network = ipaddress.ip_network(subnet.network, strict=False)
            if ip in network and network.prefixlen > best_prefix:
                best_match, best_prefix = subnet, network.prefixlen
        except ValueError:
            continue
    return best_match


def _find_gateway_device_for_ip(ip_str: str) -> Device | None:
    """
    通过IP查找网关设备

    查找IP所在子网的gateway，再通过gateway地址找到对应设备。
    """
    try:
        ipaddress.ip_address(ip_str)
    except ValueError:
        return None

    subnet = _find_subnet_for_ip(ip_str)
    if not subnet or not subnet.gateway:
        return None

    return _find_device_for_ip(subnet.gateway)


def _find_device_for_ip(ip_str: str) -> Device | None:
    """通过IP查找设备"""
    try:
        ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    # 显式 pk 序：不依赖模型默认排序，保持「取最早创建记录」的原有语义
    interface = Interface.objects.select_related("device").filter(ip_address=ip_str).order_by("pk").first()
    return interface.device if interface else None


def _find_device_by_interface(device: Device, interface_name: str) -> Device | None:
    """通过接口名查找连接的设备"""
    interface = Interface.objects.filter(device=device, interface=interface_name).first()
    if interface and interface.ip_address:
        return _find_device_for_ip(interface.ip_address)
    return None


def _find_vrf_for_ip(ip_str: str) -> str:
    """
    通过IP查找所属VRF（从Subnet表查询）

    Subnet表有0.0.0.0/0兜底，必定命中，无需Interface表回退。

    优先级：
    1. device → 设备VRF
    2. 专线tag → 合作方VRF
    3. 0.0.0.0/0 → internet
    4. datacenter+securityzone → 路由链跟踪
    5. gateway → 网关设备VRF
    6. 其他 → default
    """
    subnet = _find_subnet_for_ip(ip_str)
    if not subnet:
        return "default"

    # 1. Subnet指定了VRF → 直接返回
    if subnet.vrf:
        return subnet.vrf

    # 2. 专线 → 合作方名称作为VRF
    tag_names = list(subnet.tags.values_list("name", flat=True))
    if "专线" in tag_names:
        return _find_vrf_from_dedicated_line(subnet)

    # 3. 0.0.0.0/0 或 ::/0 → 互联网
    try:
        network = ipaddress.ip_network(subnet.network, strict=False)
        if network.prefixlen == 0:
            return "internet"
    except ValueError:
        pass

    # 4. datacenter + securityzone → 查路由表跟踪
    if subnet.datacenter and subnet.security_zone:
        return _find_vrf_from_routing_table(ip_str, subnet)

    # 5. 有gateway → 网关设备VRF
    if subnet.gateway:
        gw_device = _find_device_for_ip(subnet.gateway)
        if gw_device:
            vrf = Vrf.objects.filter(device=gw_device, name="default").first()
            if vrf:
                return "default"
            vrf = Vrf.objects.filter(device=gw_device).order_by("pk").first()
            return vrf.name if vrf else "default"

    return "default"


def _find_vrf_from_routing_table(ip_str: str, subnet) -> str:
    """
    通过设备路由表查找VRF（datacenter + securityzone场景）

    路由链跟踪：
    查找所有包含该网段的路由，沿下一跳跟踪直到终点设备。
    终点 = 没有该网段特定路由的设备（只有默认路由）。

    举例：
      intyw-cs:default       /23 → intyw-fw
      intyw-fw:default       /23 → intyw-cs:VRF-INTYW
      intyw-cs:VRF-INTYW     /23 → intyw-slb
      intyw-slb:default      default → intyw-cs:VRF-INTYW  (无/23特定路由，是终点)

    终点: intyw-slb:default → 返回 "default"
    """
    visited: set[int] = set()  # 设备ID环路检测

    # 查找所有匹配该网段的路由，按最长前缀排序
    matching_routes = []
    subnet_network = ipaddress.ip_network(subnet.network, strict=False)
    for route in Route.objects.filter(enabled=True, destination__isnull=False).select_related("vrf__device"):
        try:
            route_network = ipaddress.ip_network(route.destination, strict=False)
            # 版本不同的路由不可能是这条目的地址的下一跳，直接跳过。
            # 这个判断不能省：ipaddress 的 subnet_of 在 IPv4/IPv6 混用时会抛
            # TypeError（"not of the same version"），原来那句 type: ignore 掩盖的
            # 正是这个真实崩溃——IPv6 静态路由遇上 IPv4 目的地址会让整个追踪接口 500。
            if route_network.version != subnet_network.version:
                continue
            if (
                route_network.subnet_of(subnet_network)  # type: ignore[arg-type, reportArgumentType]
                and subnet_network.prefixlen == route_network.prefixlen
            ):
                device_id = route.vrf.device.pk if route.vrf and route.vrf.device else None
                if device_id:
                    matching_routes.append((route, device_id, route_network.prefixlen))
        except ValueError:
            continue

    if not matching_routes:
        return ""

    # 按设备分组，每台设备取最长前缀
    device_routes: dict[int, tuple] = {}
    for route, device_id, prefixlen in matching_routes:
        if device_id not in device_routes or prefixlen > device_routes[device_id][1]:
            device_routes[device_id] = (route, prefixlen)

    # 从任意设备开始跟踪路由链
    current_device_id = next(iter(device_routes))

    for _ in range(20):  # 最多跟踪20跳
        if current_device_id in visited:
            break
        visited.add(current_device_id)

        if current_device_id not in device_routes:
            break

        route, _ = device_routes[current_device_id]

        # 下一跳是IP地址
        if route.nexthop and _is_ip_address(route.nexthop):
            next_device = _find_device_for_ip(route.nexthop)
            if not next_device:
                break
            next_device_id = next_device.pk
        # 下一跳是接口
        elif route.interface:
            device = route.vrf.device if route.vrf else None
            if not device:
                break
            next_device = _find_device_by_interface(device, route.interface)
            if not next_device:
                break
            next_device_id = next_device.pk
        else:
            break

        # 下一台设备没有该网段的特定路由 → 当前设备是终点
        if next_device_id not in device_routes:
            vrf = route.vrf
            return vrf.name if vrf else "default"

        current_device_id = next_device_id

    # 找不到终点，返回最后一个设备的VRF
    if current_device_id in device_routes:
        route, _ = device_routes[current_device_id]
        return route.vrf.name if route.vrf else "default"

    return ""


def _find_vrf_from_dedicated_line(subnet) -> str:
    """
    专线合作方VRF查找

    通过专线子网的tag确定合作方名称，作为独立VRF。
    tag中应包含合作方名称，如果没有，显示未知合作方。
    """
    tag_names = list(subnet.tags.values_list("name", flat=True))
    partner_tags = [t for t in tag_names if t != "专线"]
    if partner_tags:
        return partner_tags[0]
    return "未知合作方"


def _route_cache(vrf_id: int) -> list[Route]:
    """按VRF缓存路由表"""
    cache_key = f"_routes_{vrf_id}"
    if not hasattr(_route_cache, cache_key):
        setattr(_route_cache, cache_key, list(Route.objects.filter(vrf_id=vrf_id, enabled=True)))
    return getattr(_route_cache, cache_key)


def _clear_route_cache():
    """清除路由缓存（测试用）"""
    keys = [k for k in dir(_route_cache) if k.startswith("_routes_")]
    for k in keys:
        delattr(_route_cache, k)


def _find_best_route(device: Device, dst_ip: str, vrf_name: str = "default") -> tuple[Route | None, str]:
    """在VRF中查找最精确路由（使用缓存）"""
    try:
        dst = ipaddress.ip_address(dst_ip)
    except ValueError:
        return None, vrf_name

    vrf = Vrf.objects.filter(device=device, name=vrf_name).first()
    if not vrf:
        return None, vrf_name

    best_route, best_prefix = None, -1
    for route in _route_cache(vrf.pk):
        try:
            network = ipaddress.ip_network(route.destination, strict=False)
            if dst in network and network.prefixlen > best_prefix:
                best_route, best_prefix = route, network.prefixlen
        except ValueError:
            continue
    return best_route, vrf_name


def _match_policy(src_ip: str, dst_ip: str, port: str, device: Device) -> dict | None:
    """匹配访问策略"""
    for policy in Policy.objects.filter(device=device, enabled=True).order_by("order"):
        src_ok = not policy.source_addresses.exists() or _match_address_list(src_ip, policy.source_addresses)
        dst_ok = not policy.destination_addresses.exists() or _match_address_list(dst_ip, policy.destination_addresses)
        port_ok = not policy.services.exists() or _match_service(port, policy.services)
        if src_ok and dst_ok and port_ok:
            return {
                "id": policy.pk,
                "policy_id": policy.policy_id,
                "name": policy.name,
                "action": policy.action,
            }
    return None


def _match_nat(src: str, dst: str, port: str, device: Device) -> dict | None:
    """匹配NAT规则"""
    for rule in NatRule.objects.filter(device=device, enabled=True).order_by("order"):
        src_ok = not rule.source_addresses.exists() or _match_address_list(src, rule.source_addresses)
        dst_ok = not rule.destination_addresses.exists() or _match_address_list(dst, rule.destination_addresses)
        port_ok = not rule.services.exists() or _match_service(port, rule.services)
        if src_ok and dst_ok and port_ok:
            result = {"id": rule.pk, "name": rule.name, "nat_type": rule.nat_type}
            if rule.translated_source:
                result["translated_source"] = rule.translated_source.name
            if rule.translated_destination:
                result["translated_destination"] = rule.translated_destination.name
            if rule.translated_service:
                result["translated_service"] = rule.translated_service.name
            return result
    return None


def _resolve_translated_ip(name: str) -> str | None:
    """解析NAT转换后的IP"""
    ab = AddressBook.objects.filter(name=name).order_by("pk").first()
    if not ab:
        return None
    if ab.ip_address:
        return ab.ip_address
    if ab.ip_start:
        return ab.ip_start
    if ab.children.exists():
        child = ab.children.order_by("pk").first()
        if child and child.ip_address:
            return child.ip_address
    return None


def _resolve_translated_port(name: str) -> str | None:
    """解析NAT转换后的端口。

    同名允许多行端口定义（2026-09 拆行）：跳过空 port 的 any 占位行、按 pk 序取
    首个真实定义——否则 first() 恰好命中占位时会把存在的端口答成 None。
    """
    svc = Service.objects.filter(name=name).exclude(port="").order_by("pk").first()
    return svc.port if svc else None


def _find_lb_backend(dst_ip: str, dst_port: str) -> list[dict]:
    """查找负载均衡后端"""
    # queryset 与最终拿到的实例分开命名：复用 vs 会让类型检查器把后面那个
    # Optional 实例当成 QuerySet，vs.device_id / vs.pool 就全成了属性错误
    queryset = LtmVirtualServer.objects.filter(vs_address=dst_ip)
    if dst_port:
        queryset = queryset.filter(vs_port=dst_port)
    vs = queryset.order_by("pk").first()
    if not vs:
        return []
    return [
        {"name": m.name, "address": m.address}
        for m in LtmPoolMember.objects.filter(device_id=vs.device_id, pool_name=vs.pool)
        if vs.pool
        if m.address
    ]


def _is_ip_address(s: str) -> bool:
    """判断是否为IP地址"""
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def trace_path(src_ip: str, dst_ip: str, dst_port: str, max_hops: int = MAX_HOPS) -> TraceResult:
    """
    路径追踪主函数

    流程：
    1. 整理源目地址端口
    2. 查找源目VRF，如果相同直接返回
    3. 循环：LB检查 → 策略匹配 → 路由查找 → VRF切换
    """
    result = TraceResult(final_src=src_ip, final_dst=dst_ip, final_port=dst_port)
    max_hops = min(max_hops, MAX_HOPS)
    _clear_route_cache()
    has_port = bool(dst_port)

    current_src, current_dst, current_port = src_ip, dst_ip, dst_port
    original_src = src_ip  # 原始源IP用于策略匹配
    visited_vrfs: set[str] = set()

    # 查找源目设备
    src_device = _find_gateway_device_for_ip(src_ip) or _find_device_for_ip(src_ip)
    dst_device = _find_gateway_device_for_ip(dst_ip) or _find_device_for_ip(dst_ip)

    if not src_device or not dst_device:
        result.error = "无法找到源或目的设备"
        return result

    # 同一设备直接返回
    if src_device == dst_device:
        result.hops.append(
            HopResult(
                device_name=src_device.hostname,
                device_id=src_device.pk,
                device_type=src_device.device_type,
                zone=src_device.security_zone.name if src_device.security_zone else "",
                src_before=src_ip,
                dst_before=dst_ip,
                src_after=src_ip,
                dst_after=dst_ip,
                port_before=dst_port,
                port_after=dst_port,
            )
        )
        return result

    # 查找源目VRF
    src_vrf = _find_vrf_for_ip(src_ip)
    dst_vrf = _find_vrf_for_ip(dst_ip)

    # 如果源目VRF相同，直接返回
    if src_vrf == dst_vrf:
        result.hops.append(
            HopResult(
                device_name=src_device.hostname,
                device_id=src_device.pk,
                device_type=src_device.device_type,
                zone=src_device.security_zone.name if src_device.security_zone else "",
                vrf=src_vrf,
                src_before=src_ip,
                dst_before=dst_ip,
                src_after=src_ip,
                dst_after=dst_ip,
                port_before=dst_port,
                port_after=dst_port,
            )
        )
        return result

    # 无端口时，外网源地址必须指定目的端口
    if not has_port and src_vrf == "internet":
        result.error = "请输入目的端口"
        return result

    # 使用源VRF开始追踪
    vrf_name = src_vrf

    # 主循环
    for hop_count in range(max_hops):
        # VRF环路检测
        if vrf_name in visited_vrfs:
            result.error = f"VRF环路: {vrf_name}"
            break
        visited_vrfs.add(vrf_name)

        # 1. 获取设备信息
        device_addr = ""
        if hop_count > 0:
            conn_intf = Interface.objects.filter(device=src_device, ip_address__isnull=False).order_by("pk").first()
            # ip_address 可空，直接赋值会把 None 混进 str
            device_addr = (conn_intf.ip_address or "") if conn_intf else ""

        subnet = _find_subnet_for_ip(current_src if hop_count == 0 else device_addr)
        zone = (subnet.security_zone.name if subnet and subnet.security_zone else "") or (
            src_device.security_zone.name if src_device.security_zone else ""
        )

        hop = HopResult(
            device_name=src_device.hostname,
            device_id=src_device.pk,
            device_type=src_device.device_type,
            zone=zone,
            vrf=vrf_name,
            src_before=current_src,
            dst_before=current_dst,
            port_before=current_port,
        )

        # 2. LB设备检查（无端口时跳过后端查询）
        if has_port and src_device.device_type == "slb":
            lb_backends = _find_lb_backend(current_dst, current_port)
            if lb_backends:
                hop.matched_vs = {
                    "vs_address": current_dst,
                    "vs_port": current_port,
                    "backends": lb_backends,
                }
                result.hops.append(hop)
                result.final_src, result.final_dst, result.final_port = (
                    current_src,
                    current_dst,
                    current_port,
                )
                result.lb_backend = lb_backends
                return result

        # 3. 防火墙策略匹配（无端口时跳过）
        if has_port and src_device.device_type == "firewall":
            policy = _match_policy(original_src, current_dst, current_port, src_device)
            if policy:
                hop.matched_policy = policy
                hop.action = policy["action"]
                if policy["action"] == "deny":
                    result.blocked = True
                    result.blocked_by = f"{src_device.hostname} - {policy['name']}"
                    result.hops.append(hop)
                    result.final_src, result.final_dst, result.final_port = (
                        current_src,
                        current_dst,
                        current_port,
                    )
                    return result

        # 4. NAT匹配（无端口时跳过）
        nat = _match_nat(current_src, current_dst, current_port, src_device) if has_port else None
        if nat:
            hop.matched_nat = nat
            if nat["nat_type"] == "snat" and "translated_source" in nat:
                new_src = _resolve_translated_ip(nat["translated_source"])
                if new_src:
                    hop.src_after = new_src
                    current_src = new_src
            elif nat["nat_type"] == "dnat":
                if "translated_destination" in nat:
                    new_dst = _resolve_translated_ip(nat["translated_destination"])
                    if new_dst:
                        hop.dst_after = new_dst
                        current_dst = new_dst
                if "translated_service" in nat:
                    new_port = _resolve_translated_port(nat["translated_service"])
                    if new_port:
                        hop.port_after = new_port
                        current_port = new_port

        # 5. 查找路由
        route, current_vrf = _find_best_route(src_device, current_dst, vrf_name)
        if not route:
            result.hops.append(hop)
            result.final_src, result.final_dst, result.final_port = (
                current_src,
                current_dst,
                current_port,
            )
            break

        hop.matched_route = {
            "id": route.pk,
            "destination": route.destination,
            "nexthop": route.nexthop or "",
            "interface": route.interface or "",
            "protocol": route.protocol,
        }

        # 6. 直连路由 → 尝试通过出接口查找下一跳设备
        next_device = None
        if route.nexthop and _is_ip_address(route.nexthop):
            next_device = _find_device_for_ip(route.nexthop)
            current_src = route.nexthop
        elif route.interface:
            next_device = _find_device_by_interface(src_device, route.interface)
            if next_device:
                conn_intf = Interface.objects.filter(device=src_device, interface=route.interface).first()
                if conn_intf and conn_intf.ip_address:
                    current_src = conn_intf.ip_address

        if not next_device:
            result.hops.append(hop)
            result.final_src, result.final_dst, result.final_port = (
                current_src,
                current_dst,
                current_port,
            )
            break

        # 7. 更新VRF（使用接收接口VRF，避免被覆盖）
        recv_intf_vrf = Interface.objects.filter(device=next_device, ip_address=route.nexthop).first()
        if recv_intf_vrf and recv_intf_vrf.vrf:
            # 这里要的是 VRF 名字不是 Vrf 对象：vrf_name 后面会被拿去
            # Vrf.objects.filter(name=...)、放进 visited_vrfs 集合做环路判断、
            # 以及塞进 HopResult.vrf 直接返回给接口。赋对象的话查询匹配不上、
            # 环路判断永远不成立、接口序列化还会 500。
            vrf_name = recv_intf_vrf.vrf.name
        elif current_vrf != "default":
            vrf_name = current_vrf

        # 8. 跳转
        result.hops.append(hop)
        src_device = next_device

    result.final_src = current_src
    result.final_dst = current_dst
    result.final_port = current_port
    return result
