"""VLAN 与 SNMP 保存器"""

from logging import getLogger

from .base import BaseSaver, as_list

logger = getLogger(__name__)


class VlanSaver(BaseSaver):
    """VLAN 保存器。

    模板产出只有 ``vlan_id``（有的厂商带 ``vlan_name``）::

        {"vlans": [{"vlan_id": "10"}, {"vlan_id": "20", "vlan_name": "Finance"}]}

    只有交换机模板产出 vlans（H3C / Huawei / Maipu / Ruijie），router 模板没有。
    """

    device_types = ["switch"]
    keys = ["vlans"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import Vlan
        from assets.serializers.views import VlanSerializer

        created, updated = 0, 0
        for item in as_list(parsed_data.get("vlans")):
            vid = self._safe_int(item.get("vlan_id") or item.get("vid"))
            if vid is None:
                continue
            name = item.get("vlan_name") or item.get("name") or ""
            is_new = self.upsert(VlanSerializer, Vlan, device, {"vid": vid}, {"vid": vid, "name": name})
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)


class SnmpConfigSaver(BaseSaver):
    """SNMP 保存器。

    SnmpConfig 是**每设备一条**，所以整组产出聚合到一条记录上。各厂商产出结构
    差别较大，两种形态都兼容：

    - Huawei / H3C router：``{"community": "public", "access_type": "read", "host_ip": ...}``
      （``access_type`` 是 read/write，决定写进读社区还是写社区）
    - H3C switch（Comware V7）：``{"version": ..., "target_hosts": [{"ip": ..., "securityname": ...}]}``
      用 target-host + securityname 表达，没有 community 字段
    """

    device_types = ["switch", "router"]
    keys = ["snmp"]

    def save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import SnmpConfig
        from assets.serializers.views import SnmpConfigSerializer

        entries = as_list(parsed_data.get("snmp"))
        if not entries:
            return (0, 0)

        payload: dict = {}
        for item in entries:
            self._collect_community(payload, item)
            self._collect_target_hosts(payload, item)
            version = self._normalize_version(item.get("version") or item.get("snmp_version"))
            if version:
                payload["version"] = version

        if not payload:
            return (0, 0)

        is_new = self.upsert(SnmpConfigSerializer, SnmpConfig, device, {}, payload)
        return (1, 0) if is_new else (0, 1)

    def _collect_community(self, payload: dict, item: dict) -> None:
        community = item.get("community")
        if not community:
            return
        access_type = str(item.get("access_type") or "").lower()
        payload["community_write" if access_type == "write" else "community_read"] = community

        host = self._safe_ip(item.get("host_ip"))
        if host:
            payload.setdefault("trap_server", host)
            payload["trap_enabled"] = True

    def _collect_target_hosts(self, payload: dict, item: dict) -> None:
        for target in as_list(item.get("target_hosts")):
            address = self._safe_ip(target.get("ip"))
            if not address:
                continue
            payload.setdefault("trap_server", address)
            payload["trap_enabled"] = True
            security_name = target.get("securityname")
            if security_name:
                payload.setdefault("community_read", security_name)

    def _normalize_version(self, value) -> str | None:
        """模板可能给 v2c / 2c / 3，统一成模型 choices 里的形式"""
        text = str(value or "").strip().lower().removeprefix("v")
        return f"v{text}" if text in {"1", "2c", "3"} else None
