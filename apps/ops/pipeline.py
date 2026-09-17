"""配置处理流水线：读 Git → 解析 → 分发 Saver。

``signals.py`` 的 post_save 接收器与管理命令 ``reparse`` 共用这一份逻辑。
抽出来的原因有两个：一是重跑时不必再去伪造 ``created`` 标志骗过信号，
二是失败原因能作为返回值带出来——信号里只打日志，而批量重跑需要知道
具体是哪台设备、哪个 key 失败。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SaverOutcome:
    """单个 Saver 的执行结果"""

    keys: list[str]
    created: int = 0
    updated: int = 0
    error: str = ""

    @property
    def label(self) -> str:
        return ",".join(self.keys)


@dataclass
class PipelineResult:
    """一次流水线的整体结果"""

    parsed: bool = False
    config_json: dict[str, Any] = field(default_factory=dict)
    outcomes: list[SaverOutcome] = field(default_factory=list)
    # 未执行的原因（堆叠备机 / Git 无配置 / 无匹配解析器）
    skipped: str = ""

    @property
    def errors(self) -> list[SaverOutcome]:
        return [outcome for outcome in self.outcomes if outcome.error]

    @property
    def created(self) -> int:
        return sum(outcome.created for outcome in self.outcomes)

    @property
    def updated(self) -> int:
        return sum(outcome.updated for outcome in self.outcomes)


def run_config_pipeline(device, device_config, *, force_parse: bool = False) -> PipelineResult:
    """对一条 DeviceConfig 执行「解析 → 分发 Saver」。

    ``force_parse=True`` 时忽略已有的 ``config_json`` 重新解析（改了 TTP 模板、
    或补上设备的厂商/型号之后需要），否则只在 ``config_json`` 为空时解析。

    堆叠组备机的配置归属主设备，这类设备直接跳过并写进 ``result.skipped``。
    """
    result = PipelineResult()

    from ops.config_owner import resolve_config_owner

    owner = resolve_config_owner(device)
    if owner.pk != device.pk:
        result.skipped = f"堆叠备机，配置归属 {owner.hostname}"
        logger.warning("设备 %s 跳过解析：%s", device.hostname, result.skipped)
        return result

    config_json = device_config.config_json if isinstance(device_config.config_json, dict) else {}
    if force_parse or not config_json:
        config_json = _parse_config(device, device_config, result)
        if not config_json:
            return result

    result.config_json = config_json
    _dispatch_savers(device, config_json, result)
    return result


def _parse_config(device, device_config, result: PipelineResult) -> dict:
    """从 Git 取配置原文并解析，成功后写回 config_json"""
    from ops.config_repo import get_config

    commit_hash = device_config.git_commit_hash
    raw_text = get_config(device.hostname, commit_hash)
    if not raw_text:
        short = commit_hash[:8] if commit_hash else "None"
        result.skipped = f"Git 无配置 (hash={short})"
        logger.warning("DeviceConfig %s: %s", device_config.pk, result.skipped)
        return {}

    from ops.parsers.factory import ParserFactory

    try:
        parser = ParserFactory.get_parser(device)
    except ValueError as e:
        result.skipped = f"无匹配解析器: {e}"
        logger.warning("设备 %s %s", device.hostname, result.skipped)
        return {}

    config_json = parser.parse(raw_text)
    if not isinstance(config_json, dict):
        config_json = {}
    device_config.config_json = config_json
    device_config.save(update_fields=["config_json", "updated_at"])
    result.parsed = True
    logger.info("设备 %s 配置解析完成", device.hostname)
    return config_json


def _dispatch_savers(device, config_json: dict, result: PipelineResult) -> None:
    """按顶层 key 找到 Saver 并逐个执行；单个失败只记录，不中断其余"""
    from ops.savers.registry import get_savers_for_config

    for keys, saver in get_savers_for_config(device.device_type, config_json):
        # 命中同一 Saver 的多个键要一起传，否则 Saver 内的兜底链只看到第一个
        payload = {key: config_json[key] for key in keys if config_json.get(key)}
        if not payload:
            continue

        outcome = SaverOutcome(keys=list(keys))
        try:
            outcome.created, outcome.updated = saver.save(device, payload)
            logger.info(
                "设备 %s [%s] 保存完成: +%d ~%d", device.hostname, outcome.label, outcome.created, outcome.updated
            )
        except Exception as e:
            outcome.error = str(e)
            logger.error("设备 %s [%s] 保存失败: %s", device.hostname, outcome.label, e, exc_info=True)
        result.outcomes.append(outcome)
