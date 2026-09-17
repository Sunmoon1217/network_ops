"""路由数据保存器"""

import ipaddress
from logging import getLogger

from assets.models import Vrf

from .base import BaseSaver, as_list

logger = getLogger(__name__)


class VrfSaver(BaseSaver):
    device_types = ["switch", "router"]
    keys = ["vrfs", "vpn_instances"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        vrfs = as_list(parsed_data.get("vrfs") or parsed_data.get("vpn_instances"))
        if not vrfs:
            return (0, 0)

        created, updated = 0, 0
        for vrf in vrfs:
            vrf_name = vrf.get("vrf", vrf.get("name"))
            if not vrf_name:
                continue
            _, is_created = Vrf.objects.update_or_create(
                device=device,
                name=vrf_name,
                defaults={
                    "rd": vrf.get("rd", ""),
                    "description": vrf.get("description", ""),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        return (created, updated)


class RouteSaver(BaseSaver):
    """静态路由保存器。

    模板产出形如 ``{"destination_network": "10.0.0.0", "mask": "255.255.0.0",
    "next_hop": "10.0.0.1"}``（Maipu / Ruijie 用的是 ``subnet_mask``，cisco 的还带
    ``interface_name`` 与 ``metric``）。

    Route 通过 ``vrf`` 表达归属，继承来的 ``device`` 与之冗余；产出里没有 VRF 信息，
    统一挂到该设备的 ``default`` VRF（不存在就建一个），与数据迁移时的回填口径一致。
    """

    device_types = ["switch", "router", "firewall"]
    keys = ["static_routes"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import Route
        from assets.serializers.views import RouteSerializer

        routes = as_list(parsed_data.get("static_routes"))
        if not routes:
            return (0, 0)

        vrf, _ = Vrf.objects.get_or_create(device=device, name="default")

        created, updated = 0, 0
        for item in routes:
            mask = item.get("mask") or item.get("subnet_mask")
            destination = self._to_cidr(item.get("destination_network"), mask)
            if not destination:
                continue
            nexthop = self._safe_ip(item.get("next_hop"))
            payload = {
                "destination": destination,
                "nexthop": nexthop,
                "interface": item.get("interface_name") or "",
                "protocol": "static",
                "metric": self._safe_int(item.get("metric")) or 0,
            }
            is_new = self.upsert(
                RouteSerializer,
                Route,
                device,
                {"vrf": vrf, "destination": destination, "nexthop": nexthop},
                {**payload, "vrf": vrf.pk},
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _to_cidr(self, network, mask) -> str | None:
        """把「网络地址 + 掩码」合成 CIDR；已经是 CIDR 的原样返回"""
        text = str(network or "").strip()
        if not text:
            return None
        if "/" in text:
            return text
        if not mask:
            return None
        try:
            return str(ipaddress.ip_network(f"{text}/{mask}", strict=False))
        except ValueError:
            return None
