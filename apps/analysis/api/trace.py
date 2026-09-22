"""路径追踪 + 路由采集 API"""

import logging

import requests
from django.db import transaction
from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def path_trace(request):
    """路径追踪: GET /api/trace/?src=&dst=&port="""
    src_ip = request.query_params.get("src", "").strip()
    dst_ip = request.query_params.get("dst", "").strip()
    dst_port = request.query_params.get("port", "").strip()

    if not src_ip or not dst_ip:
        return Response({"error": "src and dst 参数必填"}, status=http_status.HTTP_400_BAD_REQUEST)

    from analysis.path_tracer import trace_path

    result = trace_path(src_ip, dst_ip, dst_port)

    return Response(
        {
            "hops": [
                {
                    "device_name": h.device_name,
                    "device_id": h.device_id,
                    "device_type": h.device_type,
                    "zone": h.zone,
                    "vrf": h.vrf,
                    "matched_policy": h.matched_policy,
                    "matched_nat": h.matched_nat,
                    "matched_route": h.matched_route,
                    "matched_vs": h.matched_vs,
                    "action": h.action,
                    "src_before": h.src_before,
                    "src_after": h.src_after,
                    "dst_before": h.dst_before,
                    "dst_after": h.dst_after,
                    "port_before": h.port_before,
                    "port_after": h.port_after,
                }
                for h in result.hops
            ],
            "final_src": result.final_src,
            "final_dst": result.final_dst,
            "final_port": result.final_port,
            "blocked": result.blocked,
            "blocked_by": result.blocked_by,
            "lb_backend": result.lb_backend,
            "error": result.error,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def route_collect(request):
    """路由采集: 从外部服务获取路由表，TTP 解析后保存

    POST /api/trace/route-collect/
    Body: {
        "device_id": 1,
        "api_url": "http://10.0.0.1/api/routing-table",
        "template": "route",
        "vrf_name": "default"
    }
    """
    device_id = request.data.get("device_id")
    api_url = request.data.get("api_url", "")
    template_name = request.data.get("template", "route")
    vrf_name = request.data.get("vrf_name", "default")

    if not device_id:
        return Response({"error": "device_id 必填"}, status=http_status.HTTP_400_BAD_REQUEST)

    from assets.models import Device, Route, Vrf

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({"error": f"设备 {device_id} 不存在"}, status=http_status.HTTP_404_NOT_FOUND)

    # 从外部 API 获取路由数据
    raw_text = ""
    if api_url:
        try:
            resp = requests.get(api_url, timeout=30, verify=False)
            resp.raise_for_status()
            raw_text = resp.text
        except requests.RequestException as e:
            logger.error("获取路由数据失败: %s - %s", api_url, e)
            return Response({"error": f"获取路由数据失败: {e}"}, status=http_status.HTTP_502_BAD_GATEWAY)

    if not raw_text:
        return Response({"error": "未获取到路由数据"}, status=http_status.HTTP_400_BAD_REQUEST)

    # TTP 解析
    try:
        from ttp import ttp

        # 模板是 ops 解析管道的资产，路径经其公开常量取（analysis → ops 单向依赖）。
        # 别再手算相对路径：拆出 app 后 `parent.parent` 已指错——同「测试内资源定位」的坑。
        from ops.parsers.template_keys import TMPLS_DIR

        template_path = None
        for subdir in ("configs", "running"):
            candidate = TMPLS_DIR / subdir / f"{template_name}.ttp"
            if candidate.exists():
                template_path = str(candidate)
                break
        if not template_path:
            return Response({"error": f"模板 {template_name}.ttp 不存在"}, status=http_status.HTTP_400_BAD_REQUEST)

        parser = ttp(data=raw_text, template=template_path)
        parser.parse()
        parsed = parser.result(format="raw")
    except Exception as e:
        logger.error("TTP 解析失败: %s", e)
        return Response({"error": f"TTP 解析失败: {e}"}, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 保存路由。**整段放进一个事务**：原先 delete 在前、逐条 create 在后，任何一条插入
    # 失败都会留下「旧路由已删、新路由一条没进」的空表，而异常被吞进 errors，接口还返回
    # success=true。现在失败会整体回滚并返回非 2xx。
    #
    # device 必须显式传：Route.device 自 migration 0023 起是非空外键（与 vrf.device 冗余，
    # Saver 里也是按 vrf.device 保持一致），漏传会撞 NotNullViolation。
    vrf, _ = Vrf.objects.get_or_create(device=device, name=vrf_name)

    routes_data = parsed[0].get("routes", []) if isinstance(parsed, list) and parsed else []

    # 同批内按 (destination, nexthop) 去重（后来者覆盖）：Route 上有
    # uni_route_vrf_dst_nh，重复行会让整批 bulk_create 失败。
    routes: dict[tuple[str, str | None], Route] = {}
    for route in routes_data:
        destination = route.get("destination", "")
        if not destination:
            continue
        nexthop = route.get("nexthop") or None
        protocol = route.get("protocol", "other")
        metric = route.get("metric", 0)
        routes[(destination, nexthop)] = Route(
            vrf=vrf,
            device=device,
            destination=destination,
            nexthop=nexthop,
            interface=route.get("interface", ""),
            protocol=protocol if protocol in dict(Route.PROTOCOL_CHOICES) else "other",
            metric=int(metric) if metric else 0,
        )

    try:
        with transaction.atomic():
            old_count = Route.objects.filter(vrf=vrf).count()
            Route.objects.filter(vrf=vrf).delete()
            Route.objects.bulk_create(list(routes.values()))
    except Exception as e:
        logger.exception("保存路由失败: device=%s vrf=%s", device.hostname, vrf_name)
        return Response(
            {"error": f"保存路由失败（原有路由未被改动）: {e}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "success": True,
            "device": device.hostname,
            "api_url": api_url,
            "vrf": vrf_name,
            "deleted": old_count,
            "created": len(routes),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def route_collect_raw(request):
    """路由采集（直接提交文本）: POST /api/trace/route-collect-raw/
    Body: {"device_id": 1, "raw_text": "...", "vrf_name": "default"}
    """
    device_id = request.data.get("device_id")
    raw_text = request.data.get("raw_text", "")
    vrf_name = request.data.get("vrf_name", "default")

    if not device_id or not raw_text:
        return Response({"error": "device_id 和 raw_text 必填"}, status=http_status.HTTP_400_BAD_REQUEST)

    from assets.models import Device, Route, Vrf

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return Response({"error": f"设备 {device_id} 不存在"}, status=http_status.HTTP_404_NOT_FOUND)

    vrf, _ = Vrf.objects.get_or_create(device=device, name=vrf_name)

    import re

    pattern = re.compile(r"^[A-Z*]+\s+(\S+)\s+(?:\[\d+/\d+\]\s+)?(?:via\s+(\S+)|is\s+directly\s+connected,\s+(\S+))")

    # 与 route_collect 同一条保存路径：一个事务 + 同批去重 + 显式带上 device。
    routes: dict[tuple[str, str | None], Route] = {}
    for line in raw_text.strip().splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        destination = m.group(1)
        nexthop = m.group(2) or None
        interface = m.group(3) or ""
        routes[(destination, nexthop)] = Route(
            vrf=vrf,
            device=device,
            destination=destination,
            nexthop=nexthop,
            interface=interface,
            protocol="connected" if interface else "static",
        )

    try:
        with transaction.atomic():
            old_count = Route.objects.filter(vrf=vrf).count()
            Route.objects.filter(vrf=vrf).delete()
            Route.objects.bulk_create(list(routes.values()))
    except Exception as e:
        logger.exception("保存路由失败（raw）: device=%s vrf=%s", device.hostname, vrf_name)
        return Response(
            {"error": f"保存路由失败（原有路由未被改动）: {e}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "success": True,
            "device": device.hostname,
            "vrf": vrf_name,
            "deleted": old_count,
            "created": len(routes),
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def route_list(request):
    """路由列表: GET /api/trace/routes/?device_id=&vrf=&protocol="""
    from assets.models import Route

    qs = Route.objects.select_related("vrf", "vrf__device").all()
    device_id = request.query_params.get("device_id")
    vrf_name = request.query_params.get("vrf")
    protocol = request.query_params.get("protocol")

    if device_id:
        qs = qs.filter(vrf__device_id=device_id)
    if vrf_name:
        qs = qs.filter(vrf__name=vrf_name)
    if protocol:
        qs = qs.filter(protocol=protocol)

    data = [
        {
            "id": r.pk,
            "device": r.vrf.device.hostname,
            "vrf": r.vrf.name,
            "destination": r.destination,
            "nexthop": r.nexthop,
            "interface": r.interface,
            "protocol": r.protocol,
            "metric": r.metric,
        }
        for r in qs[:500]
    ]
    return Response({"routes": data, "total": qs.count()})


@api_view(["GET"])
@permission_classes([AllowAny])
def dns_query(request):
    """DNS 查询: GET /api/trace/dns-query/?domain=&type=&server="""
    domain = request.query_params.get("domain", "").strip()
    record_type = request.query_params.get("type", "A").strip().upper()
    dns_server = request.query_params.get("server", "").strip()

    if not domain:
        return Response({"error": "domain 参数必填"}, status=400)

    results = []

    # 优先使用 dnspython（支持指定 DNS 服务器）
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver()
        if dns_server:
            resolver.nameservers = [dns_server]

        answers = resolver.resolve(domain, record_type)
        ttl = getattr(answers.response.answer[0], "ttl", 0)
        for rdata in answers:
            results.append({"type": record_type, "name": domain, "value": str(rdata), "ttl": str(ttl)})
    except ImportError:
        # dnspython 未安装，回退到 socket（仅 A/AAAA，不支持指定服务器）
        if record_type not in ("A", "AAAA"):
            return Response({"error": "dnspython 未安装，仅支持 A/AAAA 查询"}, status=501)
        import socket

        try:
            infos = socket.getaddrinfo(domain, None, socket.AF_INET if record_type == "A" else socket.AF_INET6)
            seen = set()
            for info in infos:
                addr = info[4][0]
                if addr not in seen:
                    seen.add(addr)
                    results.append({"type": record_type, "name": domain, "value": addr, "ttl": "-"})
            else:
                try:
                    import dns.resolver

                    answers = dns.resolver.resolve(domain, record_type)
                    for rdata in answers:
                        results.append(
                            {
                                "type": record_type,
                                "name": domain,
                                "value": str(rdata),
                                "ttl": str(getattr(answers.rrset, "ttl", "-")),
                            }
                        )
                except ImportError:
                    return Response({"error": "dnspython 未安装，仅支持 A/AAAA 查询"}, status=501)
                except Exception as e:
                    return Response({"error": f"DNS 查询失败: {e}"}, status=502)
        except socket.gaierror as e:
            return Response({"error": f"DNS 解析失败: {e}"}, status=502)
    except Exception as e:
        return Response({"error": str(e)}, status=502)

    return Response({"domain": domain, "type": record_type, "server": dns_server or "系统默认", "records": results})
