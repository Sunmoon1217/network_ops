"""链路带宽配置（``conf/links.json``）：读取、域规则校验与脱敏投影。

通用部分（路径解析 / JSON / pydantic 严格校验 / 统一异常）在 ``netops.config``；这里只保留
链路域的规则（version、scope 引用、subject 唯一、非空）与展示投影。投影 **不含
host / ifname**，所以免认证的大屏接口不会暴露现场拓扑。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from netops.config import ConfigError, StrictModel, load_json_config

CONFIG_VERSION = 1
DEFAULT_CONFIG_PATH = "conf/links.json"
PLACEHOLDER_IFNAME = "ifname"


class LinkConfigError(ConfigError):
    """链路配置缺失、不可解析或违反域规则。"""


class LinkTargetModel(StrictModel):
    """一条链路的原始配置（类型由 pydantic 严格校验，域规则在 ``_build_config``）。"""

    scope: str
    subject: str
    label: str
    host: str
    ifname: str
    enabled: bool = True


class LinkPanelModel(StrictModel):
    """一张图的原始配置。"""

    id: str
    label: str
    scopes: list[str]


class LinkConfigModel(StrictModel):
    """``conf/links.json`` 的顶层结构。"""

    version: int
    panels: list[LinkPanelModel]
    scopes: dict[str, str]
    targets: list[LinkTargetModel]


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
    from django.conf import settings

    path = Path(settings.DASHBOARD_LINKS_FILE)
    return path if path.is_absolute() else settings.BASE_DIR / path


def load_links_config(path: Path | None = None) -> LinkConfig:
    file = path or config_path()
    try:
        model = load_json_config(file, LinkConfigModel)
    except ConfigError as exc:
        raise LinkConfigError(str(exc)) from exc
    return _build_config(model, source=str(file))


def parse_links_config(data: Any, *, source: str = DEFAULT_CONFIG_PATH) -> LinkConfig:
    """校验并实例化；任何结构 / 域规则问题都带来源路径抛 ``LinkConfigError``。"""
    try:
        model = LinkConfigModel.model_validate(data)
    except ValidationError as exc:
        raise LinkConfigError(f"{source}: 字段校验失败: {exc}") from exc
    return _build_config(model, source=source)


def _build_config(model: LinkConfigModel, *, source: str) -> LinkConfig:
    """类型已由 pydantic 保证，这里只查域规则（业务语义）。"""

    def fail(message: str) -> LinkConfigError:
        return LinkConfigError(f"{source}: {message}")

    if model.version != CONFIG_VERSION:
        raise fail(f"version 必须为 {CONFIG_VERSION}（当前 {model.version!r}）")
    if not model.scopes:
        raise fail("scopes 必须是非空对象（scope slug → 中文名）")
    scopes: dict[str, str] = {}
    for scope, label in model.scopes.items():
        if not scope.strip():
            raise fail("scopes 的键不能为空")
        if not label.strip():
            raise fail(f"scopes.{scope} 的中文名不能为空")
        scopes[scope] = label.strip()

    if not model.panels:
        raise fail("panels 必须是非空数组")
    panels: list[LinkPanel] = []
    panel_ids: set[str] = set()
    for index, item in enumerate(model.panels):
        if not item.id.strip():
            raise fail(f"panels[{index}].id 不能为空")
        if item.id in panel_ids:
            raise fail(f"panels 的 id 重复: {item.id}")
        panel_ids.add(item.id)
        if not item.label.strip():
            raise fail(f"panels[{index}].label 不能为空")
        if not item.scopes:
            raise fail(f"panels[{index}].scopes 必须是非空数组")
        for scope in item.scopes:
            if scope not in scopes:
                raise fail(f"panels[{index}].scopes 引用了未定义的 scope: {scope!r}")
        panels.append(LinkPanel(id=item.id, label=item.label.strip(), scopes=tuple(item.scopes)))

    if not model.targets:
        raise fail("targets 必须是非空数组")
    targets: list[LinkTarget] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(model.targets):
        if item.scope not in scopes:
            raise fail(f"targets[{index}].scope 未在 scopes 中定义: {item.scope!r}")
        if not item.subject.strip():
            raise fail(f"targets[{index}].subject 不能为空")
        key = (item.scope, item.subject.strip())
        if key in seen:
            raise fail(f"targets 里 scope/subject 重复: {item.scope}/{item.subject}")
        seen.add(key)
        if not item.label.strip():
            raise fail(f"targets[{index}].label 不能为空")
        if not item.host.strip():
            raise fail(f"targets[{index}].host 不能为空")
        if not item.ifname.strip():
            raise fail(f"targets[{index}].ifname 不能为空")
        targets.append(
            LinkTarget(
                scope=item.scope,
                subject=item.subject.strip(),
                label=item.label.strip(),
                host=item.host.strip(),
                ifname=item.ifname.strip(),
                enabled=item.enabled,
            )
        )

    return LinkConfig(panels=tuple(panels), scopes=scopes, targets=tuple(targets))
