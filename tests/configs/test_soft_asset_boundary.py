"""软资产两段的边界守卫：计算段不认识 assets，落库段不认识 configs。

这是拆分的目的本身（``handbook/design/layering.md`` 的矩阵：``configs → assets`` ✓、
``assets → configs`` ✗），靠人眼守不住，用 AST 扫源码。

编排（``configs/services/softasset/sync.py``）**可以** import assets——那是矩阵允许的
向下调用；这里只钉住两个实现模块。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "apps" / "configs" / "services" / "softasset" / "build.py"
WRITER = ROOT / "apps" / "assets" / "services" / "softasset.py"


def _imported_modules(path: Path) -> set[str]:
    """模块里所有绝对导入的顶层模块名（相对导入一定是本包内，不算跨域）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_builder_does_not_import_assets():
    assert "assets" not in _imported_modules(BUILDER), "计算段不许认识 assets——它的产出是 kind 字符串，不是 CIType"


def test_writer_does_not_import_configs():
    assert "configs" not in _imported_modules(WRITER), "落库段不许认识 configs——它只按 kind + key 往前写"
