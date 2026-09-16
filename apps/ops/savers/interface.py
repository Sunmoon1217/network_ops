"""接口数据保存器"""

from logging import getLogger

from assets.models import Interface

from .base import BaseSaver, as_list

logger = getLogger(__name__)


class InterfaceSaver(BaseSaver):
    """接口配置保存器 - 定义 device_types/keys 即自动注册"""

    device_types = ["switch", "router", "firewall"]
    keys = ["interfaces"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        interfaces = as_list(parsed_data.get("interfaces"))
        if not interfaces:
            return (0, 0)

        created, updated = 0, 0
        for iface in interfaces:
            iface_name = iface.get("interface")
            if not iface_name:
                continue

            vlans = {}
            if iface.get("access_vlan"):
                vlans["pvid"] = self._safe_int(iface["access_vlan"])
            if iface.get("trunk_vlans"):
                vlans["trunk"] = iface["trunk_vlans"]

            mode = iface.get("mode")
            if mode == "route":
                mode = "layer3"

            enabled = iface.get("enabled")
            if isinstance(enabled, (int, float)):
                enabled = enabled == 0

            _, is_created = Interface.objects.update_or_create(
                device=device,
                interface=iface_name,
                defaults={
                    "description": iface.get("description"),
                    "enabled": bool(enabled),
                    "mode": mode or "access",
                    "vlans": vlans,
                    "ip_address": iface.get("ip_address"),
                    "subnet_mask": iface.get("subnet_mask"),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

        logger.info("接口保存完成: 新增 %d, 更新 %d", created, updated)
        return (created, updated)
