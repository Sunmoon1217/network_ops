"""接口数据保存器"""

from logging import getLogger

from assets.models import Interface

from .base import BaseSaver, as_list

logger = getLogger(__name__)


class InterfaceSaver(BaseSaver):
    """接口配置保存器 - 定义 device_types/keys 即自动注册"""

    device_types = ["switch", "router", "firewall"]
    keys = ["interfaces"]
    model_paths = ["assets.models.Interface"]

    @staticmethod
    def _entries(raw) -> list[dict]:
        """把产出归一成 ``[{interface: 名字, ...}]``。

        hillstone 模板的动态组名 ``interfaces.{{ interface }}`` 产出 ``{接口名: 内容}``
        （变量被抬成字典键、值里没有 ``interface`` 字段）——展开成平铺记录；
        普通组的平铺 dict / 列表原样返回。结构级差异留在 Saver（分层约定，
        先例 ``AddressBookSaver._entries``）。
        """
        if isinstance(raw, dict) and "interface" not in raw:
            return [{"interface": name, **(body if isinstance(body, dict) else {})} for name, body in raw.items()]
        return as_list(raw)

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        interfaces = self._entries(parsed_data.get("interfaces"))
        if not interfaces:
            return (0, 0)

        rows = []
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
            if isinstance(enabled, str):
                # 防御：模板若输出字符串 "1"/"0" 也按同一语义解析。
                # bool("0") 是 True——直接 bool() 会把禁用存成启用。
                text = enabled.strip().lower()
                enabled = None if text == "" else text not in ("0", "false", "disabled", "disable")
            elif isinstance(enabled, (int, float)):
                # 四家交换机模板（h3c/huawei/maipu/ruijie）统一输出 int：1=启用、
                # 0=禁用（set(0)/set(1)/default(1)，2026-09 实测三态 1/0/1）。
                # 旧代码 `enabled == 0` 把方向弄反了：1（启用）→ False、0（禁用）
                # → True——接口启停状态整体颠倒。
                enabled = bool(enabled)

            rows.append(
                {
                    "interface": iface_name,
                    "description": iface.get("description"),
                    "enabled": bool(enabled),
                    "mode": mode or "access",
                    "vlans": vlans,
                    "ip_address": iface.get("ip_address"),
                    "subnet_mask": iface.get("subnet_mask"),
                }
            )

        created, updated = self.bulk_upsert(Interface, device, rows, key_fields=("interface",))
        logger.info("接口保存完成: 新增 %d, 更新 %d", created, updated)
        return (created, updated)
