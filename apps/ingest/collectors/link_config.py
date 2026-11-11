"""链路带宽配置（``conf/links.json``）：读取、校验与脱敏投影的唯一入口。

- 采集侧（ingest）按 ``enabled`` 的 targets 查 Zabbix；只读接口只消费 ``meta()``
  （**不含 host / ifname**），所以免认证的大屏接口不会暴露现场拓扑。
- 路径由 ``DASHBOARD_LINKS_FILE`` 指定：容器里是 ``/etc/netops/conf/links.json``
  （compose 把宿主 ``conf/`` 只读挂进去），宿主直跑是 ``conf/links.json``；
  相对路径按 ``settings.BASE_DIR`` 解析，不依赖进程 CWD。
- 不做静默兜底：文件缺失 / JSON 写坏 / 字段非法一律抛 ``LinkConfigError``，
  由管理命令 ``refresh_link_cache --check`` 或 Celery 任务显式失败，避免把
  「配置写错了」伪装成「大屏暂无数据」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

CONFIG_VERSION = 1
DEFAULT_CONFIG_PATH = "conf/links.json"
PLACEHOLDER_IFNAME = "ifname"


class LinkConfigError(ValueError):
    """配置缺失、不可解析或字段非法。"""


@dataclass(frozen=True)
class LinkTarget:
    """一条链路：slug 是稳定数据键，label 用于展示，host / ifname 只给采集侧。"""

    scope: str
    subject: str
    label: str
    host: str
    ifname: str
    enabled: bool = True

    def meta(self) -> dict[str, Any]:
        """脱敏投影：前端只拿 slug / 中文名 / 开关。"""
        return {"scope": self.scope, "subject": self.subject, "label": self.label, "enabled": self.enabled}


@dataclass(frozen=True)
class LinkPanel:
    """一张图：包含哪些 scope、图标题是什么。"""

    id: str
    label: str
    scopes: tuple[str, ...]

    def meta(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "scopes": list(self.scopes)}


@dataclass(frozen=True)
class LinkConfig:
    panels: tuple[LinkPanel, ...]
    scopes: dict[str, str]
    targets: tuple[LinkTarget, ...]

    def enabled_targets(self) -> tuple[LinkTarget, ...]:
        return tuple(target for target in self.targets if target.enabled)

    def meta(self) -> dict[str, Any]:
        """随缓存一起下发的展示字段（不含 host / ifname）。"""
        return {
            "panels": [panel.meta() for panel in self.panels],
            "scopes": dict(self.scopes),
            "targets": [target.meta() for target in self.targets],
        }


def config_path() -> Path:
    """配置路径：DASHBOARD_LINKS_FILE 由 settings 统一注入（env 覆盖默认值）。"""
    path = Path(settings.DASHBOARD_LINKS_FILE)
    return path if path.is_absolute() else settings.BASE_DIR / path


def load_links_config(path: Path | None = None) -> LinkConfig:
    file = path or config_path()
    try:
        raw = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise LinkConfigError(f"链路配置不可读: {file}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LinkConfigError(f"链路配置不是合法 JSON: {file}: {exc}") from exc
    return parse_links_config(data, source=str(file))


def parse_links_config(data: Any, *, source: str = DEFAULT_CONFIG_PATH) -> LinkConfig:
    """校验并实例化；任何结构问题都带来源路径抛 ``LinkConfigError``。"""

    def fail(message: str) -> LinkConfigError:
        return LinkConfigError(f"{source}: {message}")

    if not isinstance(data, dict):
        raise fail("顶层必须是 JSON 对象")
    if data.get("version") != CONFIG_VERSION:
        raise fail(f"version 必须为 {CONFIG_VERSION}（当前 {data.get('version')!r}）")

    scopes_raw = data.get("scopes")
    if not isinstance(scopes_raw, dict) or not scopes_raw:
        raise fail("scopes 必须是非空对象（scope slug → 中文名）")
    scopes: dict[str, str] = {}
    for scope, label in scopes_raw.items():
        if not isinstance(scope, str) or not scope.strip():
            raise fail("scopes 的键不能为空")
        if not isinstance(label, str) or not label.strip():
            raise fail(f"scopes.{scope} 的中文名不能为空")
        scopes[scope] = label.strip()

    panels_raw = data.get("panels")
    if not isinstance(panels_raw, list) or not panels_raw:
        raise fail("panels 必须是非空数组")
    panels: list[LinkPanel] = []
    panel_ids: set[str] = set()
    for index, item in enumerate(panels_raw):
        if not isinstance(item, dict):
            raise fail(f"panels[{index}] 必须是对象")
        panel_id = item.get("id")
        label = item.get("label")
        panel_scopes = item.get("scopes")
        if not isinstance(panel_id, str) or not panel_id.strip():
            raise fail(f"panels[{index}].id 不能为空")
        if panel_id in panel_ids:
            raise fail(f"panels 的 id 重复: {panel_id}")
        panel_ids.add(panel_id)
        if not isinstance(label, str) or not label.strip():
            raise fail(f"panels[{index}].label 不能为空")
        if not isinstance(panel_scopes, list) or not panel_scopes:
            raise fail(f"panels[{index}].scopes 必须是非空数组")
        for scope in panel_scopes:
            if scope not in scopes:
                raise fail(f"panels[{index}].scopes 引用了未定义的 scope: {scope!r}")
        panels.append(LinkPanel(id=panel_id, label=label.strip(), scopes=tuple(panel_scopes)))

    targets_raw = data.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise fail("targets 必须是非空数组")
    targets: list[LinkTarget] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(targets_raw):
        if not isinstance(item, dict):
            raise fail(f"targets[{index}] 必须是对象")
        scope = item.get("scope")
        subject = item.get("subject")
        label = item.get("label")
        host = item.get("host")
        ifname = item.get("ifname")
        enabled = item.get("enabled", True)
        if scope not in scopes:
            raise fail(f"targets[{index}].scope 未在 scopes 中定义: {scope!r}")
        if not isinstance(subject, str) or not subject.strip():
            raise fail(f"targets[{index}].subject 不能为空")
        key = (scope, subject.strip())
        if key in seen:
            raise fail(f"targets 里 scope/subject 重复: {scope}/{subject}")
        seen.add(key)
        if not isinstance(label, str) or not label.strip():
            raise fail(f"targets[{index}].label 不能为空")
        if not isinstance(host, str) or not host.strip():
            raise fail(f"targets[{index}].host 不能为空")
        if not isinstance(ifname, str) or not ifname.strip():
            raise fail(f"targets[{index}].ifname 不能为空")
        if not isinstance(enabled, bool):
            raise fail(f"targets[{index}].enabled 必须是布尔值")
        targets.append(LinkTarget(scope=scope, subject=subject.strip(), label=label.strip(), host=host.strip(), ifname=ifname.strip(), enabled=enabled))

    return LinkConfig(panels=tuple(panels), scopes=scopes, targets=tuple(targets))
