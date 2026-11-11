"""跨域的结构化配置加载：读文件 → JSON → pydantic 严格校验。

放在 ``netops/`` 的理由与 ``schema.py`` 同类：这是跨 app 的项目级约定。各域定义自己的
模型并显式调用 ``load_json_config``，基建**不持有任何域模型、也不做配置注册表**——避免
隐式依赖与启动顺序问题。

两条边界：

- **不读环境变量**：可被 env 覆盖的单值只在 ``settings/base.py`` 定义，由调用方决定是否
  传给 loader；当前链路配置没有这类单值项。
- **不做进程内缓存**：配置文件很小、读取频率低（链路每 3 分钟一次），要热更新时显式重读；
  以后真需要再加 mtime 缓存并暴露 ``reload()``。
"""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

__all__ = ["ConfigError", "StrictModel", "load_json_config", "resolve_config_path"]

T = TypeVar("T", bound=BaseModel)


class ConfigError(ValueError):
    """配置文件缺失、不可解析或字段非法。"""


class StrictModel(BaseModel):
    """配置文件基类：未知字段直接报错（拼错 ``enabled`` 不会被静默忽略），类型严格。"""

    model_config = ConfigDict(extra="forbid", strict=True)


def resolve_config_path(path: str | Path) -> Path:
    """相对路径按 ``settings.BASE_DIR`` 解析，不依赖进程 CWD。"""
    from django.conf import settings

    file = Path(path)
    return file if file.is_absolute() else settings.BASE_DIR / file


def load_json_config(path: str | Path, model: type[T]) -> T:
    """读 JSON 并用 ``model`` 严格校验；任何失败都转成 ``ConfigError``（消息带文件路径）。"""
    file = resolve_config_path(path)
    try:
        raw = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"配置文件不可读: {file}（{exc}）") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON: {file}: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{file}: 字段校验失败: {exc}") from exc
