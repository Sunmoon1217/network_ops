"""配置仓库重放旧历史后，把 ``DeviceConfig.git_commit_hash`` 改指新 hash。

``DeviceConfig`` 是 configs 的表，所以回写实现住本域；core 只提供钩子与锚点查询。
两种要回写的行（正常重放 / 历史脏行）见 handbook/deploy.md「配置仓库」。
"""

import logging

from configs.models import DeviceConfig
from core import config_repo

logger = logging.getLogger(__name__)


def remap_device_config_hashes(hostname: str, mapping: dict[str, str]) -> None:
    """把该设备的 DeviceConfig 行指向重放后的新 hash（映射为空时由调用方跳过）。"""
    try:
        rows = list(DeviceConfig.objects.filter(device__hostname=hostname, git_commit_hash__in=mapping))
        for row in rows:
            row.git_commit_hash = mapping[row.git_commit_hash]
        if rows:
            DeviceConfig.objects.bulk_update(rows, ["git_commit_hash"])

        for row in DeviceConfig.objects.filter(device__hostname=hostname).exclude(git_commit_hash__in=mapping):
            anchor = config_repo.legacy_commit_for(hostname, row.git_commit_hash)
            if anchor is None:
                continue  # 假 hash（测试数据等）：保持原样，读取兜底也查不到
            new = mapping.get(anchor)
            if new and new != row.git_commit_hash:
                row.git_commit_hash = new
                row.save(update_fields=["git_commit_hash"])
    except Exception:
        logger.exception("回写 DeviceConfig.git_commit_hash 失败 hostname=%s（旧 hash 由读取兜底）", hostname)
