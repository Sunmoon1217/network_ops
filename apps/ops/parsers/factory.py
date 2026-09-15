from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

from ttp import ttp

_TMPLS_DIR = Path(__file__).resolve().parent / "tmpls"


def _get_template_path(template_name: str) -> str:
    """在 tmpls/configs 和 tmpls/running 中查找模板"""
    for subdir in ("configs", "running"):
        path = _TMPLS_DIR / subdir / template_name
        if path.exists():
            return path.as_posix()
    raise FileNotFoundError(f"模板文件不存在: {template_name}")


class BaseParser(ABC):
    """解析器基类，纯函数，无 Django 依赖"""

    template_name: str = ""

    @abstractmethod
    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析原始配置文本，返回结构化数据"""

    def _run_ttp(self, raw_text: str) -> Any:

        template_path = _get_template_path(self.template_name)
        parser = ttp(data=raw_text, template=template_path)
        parser.parse()
        return parser.result(format="raw")


class ParserFactory:
    """解析器工厂 - 根据厂商和设备类型分发到对应解析器"""

    _registry: dict[tuple[str, str], type[BaseParser]] = {}

    _vendor_aliases: dict[str, str] = {
        "H3C": "H3C",
        "华三": "H3C",
        "新华三": "H3C",
        "h3c": "H3C",
        "华为": "Huawei",
        "Huawei": "Huawei",
        "huawei": "Huawei",
        "迈普": "Maipu",
        "Maipu": "Maipu",
        "锐捷": "Ruijie",
        "Ruijie": "Ruijie",
        "思科": "Cisco",
        "Cisco": "Cisco",
        "山石": "Hillstone",
        "Hillstone": "Hillstone",
        "A10": "A10",
        "a10": "A10",
        "F5": "F5",
        "f5": "F5",
    }

    @classmethod
    def register(cls, vendor: str, device_type: str):
        def decorator(parser_cls: type[BaseParser]) -> type[BaseParser]:
            cls._registry[(vendor, device_type)] = parser_cls
            return parser_cls

        return decorator

    @classmethod
    def _normalize_vendor(cls, vendor_name: str) -> str:
        if not vendor_name:
            return ""
        if vendor_name in cls._vendor_aliases:
            return cls._vendor_aliases[vendor_name]
        lower = vendor_name.lower()
        for alias, canonical in cls._vendor_aliases.items():
            if alias.lower() == lower:
                return canonical
        return vendor_name

    @classmethod
    def get_parser(cls, device) -> BaseParser:
        vendor = device.device_model.vendor.name
        device_type = device.device_type
        normalized = cls._normalize_vendor(vendor)
        parser_cls = cls._registry.get((normalized, device_type))
        if not parser_cls:
            raise ValueError(f"未注册的解析器: vendor={vendor!r}, type={device_type!r}")
        return parser_cls()

    @classmethod
    def get_parser_by_keys(cls, vendor: str, device_type: str) -> BaseParser:
        normalized = cls._normalize_vendor(vendor)
        parser_cls = cls._registry.get((normalized, device_type))
        if not parser_cls:
            raise ValueError(f"未注册的解析器: vendor={vendor!r}, type={device_type!r}")
        return parser_cls()

    @classmethod
    def available_parsers(cls) -> list[tuple[str, str]]:
        return list(cls._registry.keys())


def _extract_ttp_result(result: list) -> dict[str, Any]:
    """从 TTP 原始结果中提取第一个匹配组的字典。"""
    if isinstance(result, list) and result:
        first_group = result[0]
        if isinstance(first_group, list) and first_group:
            return cast(dict[str, Any], first_group[0])
    return {}


@ParserFactory.register("A10", "loadbalancer")
class A10SLBParser(BaseParser):
    """A10 负载均衡配置解析器。"""

    template_name = "a10_slb.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析 A10 SLB 配置文本。

        Returns:
            包含 servers, service_groups, virtual_server 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("Cisco", "firewall")
class CiscoFWParser(BaseParser):
    """思科 ASA 防火墙配置解析器。"""

    template_name = "cisco_fw.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析思科 ASA 防火墙配置文本。

        Returns:
            包含 interfaces, static_routes, acl, nat 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("F5", "loadbalancer")
class F5GTMParser(BaseParser):
    """F5 GTM (DNS) 负载均衡配置解析器。"""

    template_name = "f5_gtm.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析 F5 GTM 配置文本。

        Returns:
            包含 datacenters, servers, pools, wideips 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("F5", "loadbalancer_ltm")
class F5LTMParser(BaseParser):
    """F5 LTM (Local Traffic Manager) 负载均衡配置解析器。"""

    template_name = "f5_ltm.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析 F5 LTM 配置文本。

        Returns:
            包含 nodes, pools, virtuals 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("H3C", "switch")
class H3CSwitchParser(BaseParser):
    """H3C Comware 交换机配置解析器。"""

    template_name = "h3c_switch.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析 H3C 交换机配置文本。

        Returns:
            包含 interfaces, vlans, vpn_instances 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("H3C", "router")
class H3CRouterParser(BaseParser):
    """H3C Comware 路由器配置解析器。"""

    template_name = "h3c_router.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析 H3C 路由器配置文本。

        Returns:
            包含 interfaces, vpn_instances, static_routes 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("Hillstone", "firewall")
class HillstoneFWParser(BaseParser):
    """山石防火墙配置解析器。"""

    template_name = "hillstone_fw.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析山石防火墙配置文本。

        Returns:
            包含 interfaces, zones, rules, addresses 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))


@ParserFactory.register("Huawei", "switch")
class HuaweiSwitchParser(BaseParser):
    """华为交换机配置解析器。"""

    template_name = "huawei_switch.ttp"

    def parse(self, raw_text: str) -> dict[str, Any]:
        """解析华为交换机配置文本。

        Returns:
            包含 interfaces, vlans, static_routes 等键的字典
        """
        return _extract_ttp_result(self._run_ttp(raw_text))
