"""Napalm 采集器"""
import logging
from typing import Any

from napalm import get_network_driver

from .base import BaseCollector, CollectResult

logger = logging.getLogger(__name__)


class NapalmCollector(BaseCollector):
    def collect(self, device, connection) -> CollectResult:
        hostname = device.hostname
        if not connection.driver:
            return CollectResult(success=False, hostname=hostname,
                                error=f"设备 {hostname} 未配置 napalm 驱动")

        logger.info("napalm 连接 %s (%s) [driver=%s]", hostname, connection.get_address(), connection.driver)
        try:
            driver = get_network_driver(connection.driver)
            optional_args: dict[str, Any] = {}
            if connection.enable_password:
                optional_args["secret"] = connection.enable_password
            if connection.extras:
                optional_args.update(connection.extras)

            napalm_device = driver(
                hostname=connection.get_address(),
                username=connection.username,
                password=connection.password,
                optional_args=optional_args,
            )
            napalm_device.open()
            try:
                config_output = napalm_device.get_config()
                config = config_output.get("running", "")
                logger.info("成功获取 %s 的配置 (长度=%d)", hostname, len(config) if config else 0)
                return CollectResult(success=True, hostname=hostname, config=config or "")
            finally:
                napalm_device.close()
        except Exception as e:
            logger.error("napalm 采集 %s 失败: %s", hostname, e, exc_info=True)
            return CollectResult(success=False, hostname=hostname, error=f"采集失败: {e}")

    def get_route_to(self, device, connection):
        return self._get_napalm_data(device, connection, "get_route_to")

    def get_arp_table(self, device, connection):
        return self._get_napalm_data(device, connection, "get_arp_table")

    def get_mac_address_table(self, device, connection):
        return self._get_napalm_data(device, connection, "get_mac_address_table")

    def get_lldp_neighbors_detail(self, device, connection):
        return self._get_napalm_data(device, connection, "get_lldp_neighbors_detail")

    def get_interfaces_counters(self, device, connection):
        return self._get_napalm_data(device, connection, "get_interfaces_counters")

    def get_environment(self, device, connection):
        return self._get_napalm_data(device, connection, "get_environment")

    def _get_napalm_data(self, device, connection, method_name: str) -> dict[str, Any]:
        hostname = device.hostname
        if not connection.driver:
            return {"success": False, "data": None, "error": f"设备 {hostname} 未配置 napalm 驱动"}
        try:
            driver = get_network_driver(connection.driver)
            optional_args: dict[str, Any] = {}
            if connection.enable_password:
                optional_args["secret"] = connection.enable_password
            if connection.extras:
                optional_args.update(connection.extras)
            napalm_device = driver(
                hostname=connection.get_address(),
                username=connection.username,
                password=connection.password,
                optional_args=optional_args,
            )
            napalm_device.open()
            try:
                method = getattr(napalm_device, method_name)
                data = method()
                return {"success": True, "data": data, "error": ""}
            finally:
                napalm_device.close()
        except Exception as e:
            logger.error("采集 %s 的 %s 失败: %s", hostname, method_name, e, exc_info=True)
            return {"success": False, "data": None, "error": f"采集失败: {e}"}
