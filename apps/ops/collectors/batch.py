"""批量设备配置采集"""
import asyncio
import logging
from dataclasses import asdict
from typing import Any

from .base import CollectResult

logger = logging.getLogger(__name__)


def _connect_and_get_config(device_info: dict[str, Any]) -> str:
    hostname = device_info.get("hostname", "unknown")
    napalm_driver = device_info.get("napalm_driver", "")
    if not napalm_driver:
        raise ValueError(f"设备 {hostname} 未配置 napalm_driver")

    from napalm import get_network_driver
    driver = get_network_driver(napalm_driver)
    optional_args = {}
    if napalm_driver in ("comware", "ios"):
        optional_args["secret"] = device_info.get("password", "")

    device = driver(
        hostname=device_info["address"],
        username=device_info["username"],
        password=device_info["password"],
        optional_args=optional_args,
    )
    device.open()
    try:
        config_output = device.get_config()
        return config_output.get("running", "") or ""
    finally:
        device.close()


async def collect_and_save(device, force: bool = False) -> CollectResult:
    from assets.models import DeviceConfig

    try:
        conn_info = device.connection
    except Exception:
        return CollectResult(device_id=device.pk, hostname=device.hostname,
                             success=False, message="未配置连接信息")

    device_info = {
        "hostname": device.hostname,
        "address": conn_info.get_address(),
        "username": conn_info.username,
        "password": conn_info.password,
        "device_type": device.device_type,
        "napalm_driver": conn_info.driver,
    }

    loop = asyncio.get_running_loop()
    try:
        config_text = await loop.run_in_executor(None, _connect_and_get_config, device_info)
    except Exception as e:
        return CollectResult(device_id=device.pk, hostname=device.hostname,
                             success=False, message=f"采集失败: {e}")

    if not config_text:
        return CollectResult(device_id=device.pk, hostname=device.hostname,
                             success=False, message="获取到空配置")

    should_save = force
    if not should_save:
        latest_config = await DeviceConfig.objects.filter(device=device).afirst()
        if latest_config is None:
            should_save = True
        else:
            from ops.config_repo import get_config
            old_config = await asyncio.to_thread(get_config, device.hostname, latest_config.git_commit_hash)
            if old_config != config_text:
                should_save = True

    if should_save:
        from ops.utils import save_deviceconfig
        try:
            await asyncio.to_thread(save_deviceconfig, device, config_text)
            new_config = await DeviceConfig.objects.filter(device=device).afirst()
            return CollectResult(device_id=device.pk, hostname=device.hostname,
                                 success=True, message="采集并保存成功",
                                 config_id=new_config.pk if new_config else None, saved=True)
        except Exception as e:
            return CollectResult(device_id=device.pk, hostname=device.hostname,
                                 success=False, message=f"保存失败: {e}")
    else:
        return CollectResult(device_id=device.pk, hostname=device.hostname,
                             success=True, message="配置未变，无需保存", saved=False)


async def batch_collect(devices: list, max_concurrent: int = 10) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _task(device):
        async with semaphore:
            return await collect_and_save(device)

    tasks = [_task(d) for d in devices]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if not isinstance(r, BaseException) and r.success)
    failed_count = len(results) - success_count
    result_list = [asdict(r) if not isinstance(r, BaseException) else {"error": str(r)} for r in results]

    return {"success": True, "total_devices": len(devices),
            "success_count": success_count, "failed_count": failed_count, "results": result_list}
