"""TTP 模板的顶层数据键提取。

只有顶层 ``<group>``（行首无缩进）会成为解析结果的键，子 group 嵌套在父节点内部。
组名可能带 TTP 语法，需要取字面前缀作为键名，例如：

    <group name="interfaces*.{{ interface }}">   →  interfaces
    <group name="src**.{{ address_type }}*">     →  src
    <group name="pools*">                        →  pools

该模块同时被契约测试与映射清单接口使用，用于校验
「解析器声明的 provides_keys」与「模板实际产出的键」是否一致。
"""

import re
from pathlib import Path

TMPLS_DIR = Path(__file__).resolve().parent / "tmpls"

# 只匹配行首无缩进的 group 声明（即顶层 group）
_TOP_GROUP_RE = re.compile(r'(?m)^<group\s+name="([^"]+)"')

# TTP 语法标记：列表后缀、动态组名表达式、层级分隔
_NAME_SEPARATORS = ("*", "{{", ".")


def find_template(template_name: str) -> Path | None:
    """在 configs / running 子目录中查找模板文件"""
    if not template_name:
        return None
    for subdir in ("configs", "running"):
        path = TMPLS_DIR / subdir / template_name
        if path.exists():
            return path
    return None


def normalize_group_name(raw: str) -> str:
    """去掉 TTP 的列表标记与动态表达式，取字面前缀作为键名"""
    name = (raw or "").strip()
    cut = len(name)
    for sep in _NAME_SEPARATORS:
        idx = name.find(sep)
        if idx != -1:
            cut = min(cut, idx)
    return name[:cut].strip()


def template_keys(template_name: str) -> list[str]:
    """返回模板的顶层键（去重，保持出现顺序）；模板不存在时返回空列表"""
    path = find_template(template_name)
    if path is None:
        return []
    keys: list[str] = []
    for raw in _TOP_GROUP_RE.findall(path.read_text(encoding="utf-8")):
        key = normalize_group_name(raw)
        if key and key not in keys:
            keys.append(key)
    return keys


def template_has_dynamic_groups(template_name: str) -> bool:
    """模板是否使用了动态 group 名（{{ ... }}），这类模板的键名只能取前缀"""
    path = find_template(template_name)
    if path is None:
        return False
    return any("{{" in raw for raw in _TOP_GROUP_RE.findall(path.read_text(encoding="utf-8")))
