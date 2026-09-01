"""Netmiko 采集器"""
import logging
from typing import Any

from netmiko import ConnectHandler

from .base import BaseCollector, CollectResult

logger = logging.getLogger(__name__)


class NetmikoCollector(BaseCollector):
    def collect(self, device, connection) -> CollectResult:
        hostname = device.hostname

        if not connection.driver:
            return CollectResult(success=False, hostname=hostname,
                                error=f"设备 {hostname} 未配置 netmiko 设备类型")

        logger.info("netmiko 连接 %s (%s) [type=%s]", hostname, connection.get_address(), connection.driver)

        try:
            params: dict[str, Any] = {
                "device_type": connection.driver,
                "host": connection.get_address(),
                "username": connection.username,
                "password": connection.password,
                "timeout": connection.timeout or 30,
            }
            if connection.enable_password:
                params["secret"] = connection.enable_password
            if connection.extras:
                params.update(connection.extras)

            conn = ConnectHandler(**params)
            conn.enable()

            vendor = ""
            if hasattr(device, "device_model") and device.device_model:
                if hasattr(device.device_model, "vendor") and device.device_model.vendor:
                    vendor = device.device_model.vendor.name

            if vendor in ("H3C",):
                output = conn.send_command("display current-configuration")
            else:
                output = conn.send_command("show running-config")

            conn.disconnect()
            logger.info("成功获取 %s 的配置 (长度=%d)", hostname, len(output) if output else 0)
            return CollectResult(success=True, hostname=hostname, config=str(output) or "")

        except Exception as e:
            logger.error("netmiko 采集 %s 失败: %s", hostname, e, exc_info=True)
            return CollectResult(success=False, hostname=hostname, error=f"采集失败: {e}")

    def get_command_output(self, device, connection, command: str) -> dict[str, Any]:
        hostname = device.hostname
        if not connection.driver:
            return {"success": False, "output": "", "error": f"设备 {hostname} 未配置 netmiko 设备类型"}
        try:
            params: dict[str, Any] = {
                "device_type": connection.driver,
                "host": connection.get_address(),
                "username": connection.username,
                "password": connection.password,
                "timeout": connection.timeout or 30,
            }
            if connection.enable_password:
                params["secret"] = connection.enable_password
            if connection.extras:
                params.update(connection.extras)
            conn = ConnectHandler(**params)
            conn.enable()
            output = conn.send_command(command)
            conn.disconnect()
            return {"success": True, "output": output, "error": ""}
        except Exception as e:
            logger.error("netmiko 命令执行失败 %s: %s", hostname, e, exc_info=True)
            return {"success": False, "output": "", "error": f"命令执行失败: {e}"}
