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


# 地址簿索引：parent_id -> 直接子节点列表（None 键为顶层地址簿）
AddressBookIndex = dict[int | None, list[AddressBook]]


def _load_addressbook_index() -> AddressBookIndex:
    """一次性把所有地址簿读入内存并按 parent_id 分组。

    地址簿匹配是递归的，逐层调用 children.all() 会每层产生一次查询（N+1），
    而调用次数是「策略数 × 地址列表数」量级，累计开销很大。
    这里一次性加载，使整个匹配过程不再访问数据库。
    """
    index: AddressBookIndex = {}
    # order_by("pk") 保证子节点顺序与原 order_by("pk").first() 的语义一致
    for ab in AddressBook.objects.only(
        "id", "name", "address_type", "ip_address", "ip_netmask", "ip_start", "ip_end", "parent_id"
    ).order_by("pk"):
        index.setdefault(ab.parent_id, []).append(ab)
    return index


def _ip_in_addressbook(
    ip, ab: AddressBook, index: AddressBookIndex, _visited: frozenset[int] | None = None, _depth: int = 0
) -> bool:
    """判断 IP 是否在地址簿中（ip 为已解析的 ipaddress 对象，避免每个节点重复解析）

    _visited 以不可变集合按分支传递：若共享同一个可变集合，菱形引用
    （多个上级地址簿引用同一个下级）在第二次遍历时会被跳过而漏匹配。
    """
    visited = _visited or frozenset()
    if _depth > MAX_ADDRESSBOOK_RECURSION or ab.pk in visited:
        return False
    visited = visited | {ab.pk}

    if ab.address_type == "host" and ab.ip_address:
        return ip == ipaddress.ip_address(ab.ip_address)
    elif ab.address_type == "subnet" and ab.ip_address and ab.ip_netmask:
        network = ipaddress.ip_network(f"{ab.ip_address}/{ab.ip_netmask}", strict=False)
        return ip in network
    elif ab.address_type == "range" and ab.ip_start and ab.ip_end:
        return int(ipaddress.ip_address(ab.ip_start)) <= int(ip) <= int(ipaddress.ip_address(ab.ip_end))
    elif ab.address_type == "addressbook":
        return any(_ip_in_addressbook(ip, child, index, visited, _depth + 1) for child in index.get(ab.pk, []))
    return False


def _match_address_list(ip_str: str, address_book, index: AddressBookIndex) -> bool:
    """匹配地址列表（IP 只解析一次，供所有顶层地址簿复用）"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(_ip_in_addressbook(ip, ab, index) for ab in address_book.all())


def _parse_port(value) -> int | None:
    """把端口文本转为整数；非数字（如 any/http）或越界时返回 None"""
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return port if 0 <= port <= 65535 else None


def _match_service(port_str: str, services) -> bool:
    """匹配服务端口（端口非法或服务写成非数字时按不匹配处理，不再抛异常）"""
    target = _parse_port(port_str)
    if target is None:
        return False
    for svc in services.all():
        if svc.port and svc.port2:
            port_range = f"{svc.port}-{svc.port2}"
        else:
            port_range = svc.port or svc.port2
        if not port_range:
            continue
        for part in str(port_range).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, _, end_text = part.partition("-")
                start, end = _parse_port(start_text), _parse_port(end_text)
                if start is not None and end is not None and start <= target <= end:
                    return True
            elif _parse_port(part) == target:
                return True
    return False


def _find_subnet_for_ip(ip_str: str) -> Subnet | None:
    """查找IP所属子网

    不使用模块级缓存：进程内缓存会在数据变更后读到过期结果（长驻进程尤其明显），
    而子网表数据量小，每次直接查询的代价可以接受。
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None

    best_match, best_prefix = None, -1
    for subnet in Subnet.objects.all():
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

    # 1. Subnet 指定了 VRF → 校验名字确实存在于 Vrf 表，避免拼写错误把追踪带偏
    if subnet.vrf and Vrf.objects.filter(name=subnet.vrf).exists():
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
            # IPv4 与 IPv6 的网络做 subnet_of 会抛 TypeError，先比对版本
            if route_network.version != subnet_network.version:
                continue
            if (
                route_network.subnet_of(subnet_network)  # type: ignore[reportArgumentType]
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

    # 起点优先取子网网关所在设备（与报文实际入口一致），避免依赖字典顺序导致结果漂移
    current_device_id = next(iter(device_routes))
    if subnet.gateway:
        gw_device = _find_device_for_ip(subnet.gateway)
        if gw_device and gw_device.pk in device_routes:
            current_device_id = gw_device.pk

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


def _match_policy(src_ip: str, dst_ip: str, port: str, device: Device, index: AddressBookIndex) -> dict | None:
    """匹配访问策略（预取 M2M，避免每条策略重复查库）"""
    policies = (
        Policy.objects.filter(device=device, enabled=True)
        .prefetch_related("source_addresses", "destination_addresses", "services")
        .order_by("order")
    )
    for policy in policies:
        src_ok = not policy.source_addresses.exists() or _match_address_list(src_ip, policy.source_addresses, index)
        dst_ok = not policy.destination_addresses.exists() or _match_address_list(
            dst_ip, policy.destination_addresses, index
        )
        # 未提供端口时视作匹配任意端口，避免漏判拦截策略
        port_ok = not port or not policy.services.exists() or _match_service(port, policy.services)
        if src_ok and dst_ok and port_ok:
            return {
                "id": policy.pk,
                "policy_id": policy.policy_id,
                "name": policy.name,
                "action": policy.action,
            }
    return None


def _match_nat(src: str, dst: str, port: str, device: Device, index: AddressBookIndex) -> dict | None:
    """匹配NAT规则（预取 M2M，避免每条规则重复查库）"""
    rules = (
        NatRule.objects.filter(device=device, enabled=True)
        .prefetch_related("source_addresses", "destination_addresses", "services")
        .order_by("order")
    )
    for rule in rules:
        src_ok = not rule.source_addresses.exists() or _match_address_list(src, rule.source_addresses, index)
        dst_ok = not rule.destination_addresses.exists() or _match_address_list(dst, rule.destination_addresses, index)
        # 未提供端口时视作匹配任意端口
        port_ok = not port or not rule.services.exists() or _match_service(port, rule.services)
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


def _resolve_translated_ip(name: str, index: AddressBookIndex) -> str | None:
    """解析NAT转换后的IP"""
    ab = AddressBook.objects.filter(name=name).order_by("pk").first()
    if not ab:
        return None
    if ab.ip_address:
        return ab.ip_address
    if ab.ip_start:
        return ab.ip_start
    for child in index.get(ab.pk, []):
        if child.ip_address:
            return child.ip_address
    return None


def _resolve_translated_port(name: str) -> str | None:
    """解析 NAT 转换后的端口：多值/范围配置时取首个可用端口"""
    svc = Service.objects.filter(name=name).first()
    if not svc:
        return None
    raw = svc.port or svc.port2
    if not raw:
        return None
    for part in str(raw).split(","):
        first = part.strip().split("-", 1)[0].strip()
        if _parse_port(first) is not None:
            return first
    return None


def _find_lb_backend(dst_ip: str, dst_port: str, device: Device | None = None) -> list[dict]:
    """查找负载均衡后端（限定在命中的 LB 设备上，避免多台 LB 同名 VIP 张冠李戴）"""
    vs = LtmVirtualServer.objects.filter(vs_address=dst_ip)
    if device is not None:
        vs = vs.filter(device=device)
    if dst_port:
        vs = vs.filter(vs_port=dst_port)
    vs = vs.order_by("pk").first()
    if not vs:
        return []
    return [
        {"name": m.name, "address": m.address}
        for m in LtmPoolMember.objects.filter(pool_name=vs.pool)
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
    # 路由缓存在单次追踪内有效，避免同一次追踪里反复查同一张 VRF 路由表
    _clear_route_cache()
    # 地址簿一次性载入内存：策略/NAT 匹配期间不再访问数据库
    addressbook_index = _load_addressbook_index()
    has_port = bool(dst_port)

    current_src, current_dst, current_port = src_ip, dst_ip, dst_port
    original_src = src_ip  # 原始源IP用于策略匹配
    # 环路检测按 (设备, VRF) 组合判断：同名 VRF（如 default）会出现在多台设备上，
    # 只比较名字会把正常的多跳转发误判为环路
    visited_hops: set[tuple[int, str]] = set()
    entry_ip = ""  # 到达当前设备的入接口地址，用于子网/安全区判定

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
        # 环路检测：同一台设备 + 同一个 VRF 再次出现才算环路
        hop_key = (src_device.pk, str(vrf_name))
        if hop_key in visited_hops:
            result.error = f"VRF环路: {src_device.hostname} / {vrf_name}"
            break
        visited_hops.add(hop_key)

        # 1. 获取设备信息：优先用实际入接口地址，其次回退到设备任一接口
        device_addr = current_src if hop_count == 0 else entry_ip
        if not device_addr:
            conn_intf = Interface.objects.filter(device=src_device, ip_address__isnull=False).order_by("pk").first()
            device_addr = conn_intf.ip_address if conn_intf else ""

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
        if has_port and src_device.device_type == "loadbalancer":
            lb_backends = _find_lb_backend(current_dst, current_port, src_device)
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

        # 3. 防火墙策略匹配（未提供端口时按任意端口处理，不再跳过）
        if src_device.device_type == "firewall":
            policy = _match_policy(original_src, current_dst, current_port, src_device, addressbook_index)
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

        # 4. NAT匹配
        nat = _match_nat(current_src, current_dst, current_port, src_device, addressbook_index)
        if nat:
            hop.matched_nat = nat
            if nat["nat_type"] == "snat" and "translated_source" in nat:
                new_src = _resolve_translated_ip(nat["translated_source"], addressbook_index)
                if new_src:
                    hop.src_after = new_src
                    current_src = new_src
            elif nat["nat_type"] == "dnat":
                if "translated_destination" in nat:
                    new_dst = _resolve_translated_ip(nat["translated_destination"], addressbook_index)
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
        # Interface.vrf 是外键，必须取 .name：直接赋对象会让后续
        # Vrf.objects.filter(name=...) 查不到而中断追踪，并把对象泄漏到响应里
        recv_intf_vrf = None
        if route.nexthop and _is_ip_address(route.nexthop):
            recv_intf_vrf = (
                Interface.objects.filter(device=next_device, ip_address=route.nexthop).select_related("vrf").first()
            )
        if recv_intf_vrf and recv_intf_vrf.vrf:
            vrf_name = recv_intf_vrf.vrf.name
        elif current_vrf != "default":
            vrf_name = current_vrf

        # 8. 跳转（记录入接口地址，供下一跳判定安全区）
        if route.nexthop and _is_ip_address(route.nexthop):
            entry_ip = route.nexthop
        elif recv_intf_vrf and recv_intf_vrf.ip_address:
            entry_ip = recv_intf_vrf.ip_address
        result.hops.append(hop)
        src_device = next_device

    result.final_src = current_src
    result.final_dst = current_dst
    result.final_port = current_port
    return result
