"""路径追踪 + 路由采集 API"""
import logging

import requests
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

    from ops.path_tracer import trace_path
    result = trace_path(src_ip, dst_ip, dst_port)

    return Response({
        "hops": [
            {
                "device_name": h.device_name, "device_id": h.device_id,
                "device_type": h.device_type, "zone": h.zone, "vrf": h.vrf,
                "matched_policy": h.matched_policy, "matched_nat": h.matched_nat,
                "matched_route": h.matched_route, "matched_vs": h.matched_vs,
                "action": h.action,
                "src_before": h.src_before, "src_after": h.src_after,
                "dst_before": h.dst_before, "dst_after": h.dst_after,
                "port_before": h.port_before, "port_after": h.port_after,
            }
            for h in result.hops
        ],
        "final_src": result.final_src, "final_dst": result.final_dst,
        "final_port": result.final_port, "blocked": result.blocked,
        "blocked_by": result.blocked_by, "lb_backend": result.lb_backend,
        "error": result.error,
    })


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
        from pathlib import Path

        from ttp import ttp

        tmpls_dir = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"
        template_path = None
        for subdir in ("configs", "running"):
            candidate = tmpls_dir / subdir / f"{template_name}.ttp"
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

    # 保存路由
    vrf, _ = Vrf.objects.get_or_create(device=device, name=vrf_name)
    old_count = Route.objects.filter(vrf=vrf).count()
    Route.objects.filter(vrf=vrf).delete()

    routes_data = []
    if parsed and isinstance(parsed, list) and len(parsed) > 0:
        routes_data = parsed[0].get("routes", [])

    created = 0
    errors = []
    for route in routes_data:
        destination = route.get("destination", "")
        nexthop = route.get("nexthop")
        interface = route.get("interface", "")
        protocol = route.get("protocol", "other")
        metric = route.get("metric", 0)

        if not destination:
            continue
        try:
            Route.objects.create(
                vrf=vrf, destination=destination, nexthop=nexthop or None,
                interface=interface,
                protocol=protocol if protocol in dict(Route.PROTOCOL_CHOICES) else "other",
                metric=int(metric) if metric else 0,
            )
            created += 1
        except Exception as e:
            errors.append(str(e))

    return Response({
        "success": True, "device": device.hostname,
        "api_url": api_url, "vrf": vrf_name,
        "deleted": old_count, "created": created, "errors": errors,
    })


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
    old_count = Route.objects.filter(vrf=vrf).count()
    Route.objects.filter(vrf=vrf).delete()

    import re
    created = 0
    errors = []

    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(
            r'^[A-Z*]+\s+(\S+)\s+(?:\[\d+/\d+\]\s+)?(?:via\s+(\S+)|is\s+directly\s+connected,\s+(\S+))',
            line
        )
        if not m:
            continue
        destination = m.group(1)
        nexthop = m.group(2)
        interface = m.group(3) or ""
        protocol = "connected" if interface else "static"

        try:
            Route.objects.create(
                vrf=vrf, destination=destination, nexthop=nexthop if nexthop else None,
                interface=interface, protocol=protocol,
            )
            created += 1
        except Exception as e:
            errors.append(str(e))

    return Response({
        "success": True, "device": device.hostname, "vrf": vrf_name,
        "deleted": old_count, "created": created, "errors": errors,
    })


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
            "id": r.pk, "device": r.vrf.device.hostname, "vrf": r.vrf.name,
            "destination": r.destination, "nexthop": r.nexthop,
            "interface": r.interface, "protocol": r.protocol, "metric": r.metric,
        }
        for r in qs[:500]
    ]
    return Response({"routes": data, "total": qs.count()})


@api_view(["GET"])
@permission_classes([AllowAny])
def dns_query(request):
    """DNS 查询: GET /api/trace/dns-query/?domain=example.com&type=A"""
    domain = request.query_params.get("domain", "").strip()
    record_type = request.query_params.get("type", "A").strip().upper()

    if not domain:
        return Response({"error": "domain 参数必填"}, status=400)

    import socket

    results = []
    try:
        if record_type in ("A", "AAAA"):
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
                    results.append({"type": record_type, "name": domain, "value": str(rdata), "ttl": str(answers.rrset.ttl)})
            except ImportError:
                return Response({"error": "dnspython 未安装，仅支持 A/AAAA 查询"}, status=501)
            except Exception as e:
                return Response({"error": f"DNS 查询失败: {e}"}, status=502)
    except socket.gaierror as e:
        return Response({"error": f"DNS 解析失败: {e}"}, status=502)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

    return Response({"domain": domain, "type": record_type, "records": results})
