"""配置仓库重放旧历史后，把 ``DeviceConfig.git_commit_hash`` 改指新 hash。

**为什么在 configs 而不是 core**：``DeviceConfig`` 是 configs 的表。core 的
``config_repo`` 只提供两个钩子点——「重放完成 + 新老 hash 映射」（``register_hash_remapper``）
与「旧共享仓库里某 hash 的锚点提交」（``legacy_commit_for``），自己不认识任何业务模型，
这样 core 才能保持「零业务依赖」（``tests/core/test_layering.py`` 守着）。

两种要回写的行：

1. **正常重放**：hash 在映射表里，直接换成重放后的 hash；
2. **脏行**（历史 bug：内容未变时早退返回 HEAD，拿到的是别的设备的 commit）：那个 hash
   没被重放，先用 ``legacy_commit_for`` 反查「≤ 该时点、真正改过本设备文件」的提交，
   再按映射换成重放后的版本。

回写失败的旧 hash 不会让数据丢失：``core.config_repo.get_config`` / ``diff_configs``
查不到时会回退读旧共享仓库。
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
