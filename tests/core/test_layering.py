"""分层守卫：core 是叶子节点，不许 import 任何业务域。

对应 ``handbook/design/layering.md`` 的依赖矩阵第一行（core 对所有业务域都是 ✗）。
这条约束靠人眼守不住——一次「顺手 import 一下」就回来了，所以用 AST 扫一遍源码。

只扫**运行期真的会执行**的 import：``TYPE_CHECKING`` 里的注解 import 与模型上的字符串
引用（``ForeignKey("assets.Device")``）不在此列，后者是已知遗留债，单独有用例标出。
运维工具例外见 ``OPERATIONAL_EXCEPTIONS``——精确到「文件 + 模块」，且例外失效会报错。
"""

import ast
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).resolve().parents[2] / "apps" / "core"
PROJECT_ROOT = CORE_DIR.parent.parent
DOMAIN_APPS = {"assets", "configs", "ingest", "egest", "analysis", "docs", "cloud"}

#: 跨域运维工具例外：与 ``layering.md``「例外与豁免」同源。
#: ``queue_*`` 两个巡检命令读的是 analysis 的访问流指标，而那是 platform 级的队列巡检
#: （AGENTS.md 约定「运维命令统一放 core」）——采集逻辑与 API / 前端卡片同源，
#: 复制一份到 core 会让同一份口径裂成两处实现。精确到 (文件, 模块) 而不是整个目录。
OPERATIONAL_EXCEPTIONS: set[tuple[str, str]] = {
    ("apps/core/management/commands/queue_status.py", "analysis.queue_monitor"),
    ("apps/core/management/commands/queue_backlog.py", "analysis.queue_monitor"),
}


def _imported_modules(tree: ast.AST):
    """产出 (行号, 模块名)：只保留绝对导入（相对导入一定是本包内）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.lineno, node.module


def _scan_core():
    """返回 (违规列表, 命中的例外集合)。"""
    offenders: list[str] = []
    hit_exceptions: set[tuple[str, str]] = set()
    for path in sorted(CORE_DIR.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, module in _imported_modules(tree):
            if module.split(".")[0] not in DOMAIN_APPS:
                continue
            if (rel, module) in OPERATIONAL_EXCEPTIONS:
                hit_exceptions.add((rel, module))
                continue
            offenders.append(f"{rel}:{lineno} → {module}")
    return offenders, hit_exceptions


def test_core_imports_no_domain_app():
    offenders, _ = _scan_core()

    assert not offenders, "core 出现业务域依赖（应改为「业务域在 ready() 里注册」或「由调用方传入」）：\n" + "\n".join(offenders)


def test_operational_exceptions_are_still_needed():
    """例外白名单不许腐化：例外修好了/命令搬走了，白名单必须跟着删。

    否则它会变成一张「这里随便跨域」的永久通行证。
    """
    _, hit = _scan_core()

    assert hit == OPERATIONAL_EXCEPTIONS, (
        "运维例外清单与实际不符——已消失的例外要删掉：\n"
        f"  清单里有但代码里没有：{sorted(OPERATIONAL_EXCEPTIONS - hit)}\n"
        f"  代码里有但清单没记：{sorted(hit - OPERATIONAL_EXCEPTIONS)}"
    )


def test_known_debt_task_device_fk_still_points_at_assets():
    """已知遗留债：``Task.device`` 仍是到 ``assets.Device`` 的外键。

    ``task-framework.md`` 步骤 3（方案 C：``target_type`` + ``target_id``）落地时，
    这条用例要删掉——它存在只是为了让「分层没做完」这件事在测试里也留个记号。
    """
    from core.models import Task

    # getattr 而非直接属性链：``related_model`` 在类型存根里被标成可能为 None
    field: Any = Task._meta.get_field("device")
    related: Any = field.related_model
    assert related is not None, "Task.device 已经没有外键目标了？方案 C 落地后请删掉本用例"
    assert related._meta.label_lower == "assets.device"
