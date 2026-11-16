"""分层守卫：core 是叶子节点，不许 import 任何业务域。

对应 ``handbook/design/layering.md`` 的依赖矩阵第一行（core 对所有业务域都是 ✗）。
这条约束靠人眼守不住——一次「顺手 import 一下」就回来了，所以用 AST 扫一遍源码。

只扫**运行期真的会执行**的 import：``TYPE_CHECKING`` 里的注解 import 不在此列。
模型层的同类约束由 ``test_core_models_have_no_cross_domain_foreign_key`` 守——字符串外键
（``ForeignKey("assets.Device")``）不是 import，AST 扫不到，但一样会把 core 绑死在上层域上。
运维工具例外见 ``OPERATIONAL_EXCEPTIONS``——精确到「文件 + 模块」，且例外失效会报错。
"""

import ast
from pathlib import Path

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


def test_core_models_have_no_cross_domain_foreign_key():
    """core 的模型上不许再挂业务域外键。

    曾经的 ``Task.device → assets.Device`` 是 ``handbook/tasks.md``（作用目标软引用）要消掉的
    债：外键一挂，core 就永远依赖 assets，字符串引用又不会被 AST 扫到。现在作用目标改成了
    ``target_type`` / ``target_id`` 软引用，这条用例守着「不许再挂回去」。
    """
    from django.apps import apps as django_apps

    offenders = [
        f"{model._meta.label}.{field.name} → {related._meta.label}"
        for model in django_apps.get_app_config("core").get_models()
        for field in model._meta.get_fields()
        if (related := getattr(field, "related_model", None)) is not None and related._meta.app_label in DOMAIN_APPS
    ]

    assert not offenders, "core 模型出现跨域外键（应改软引用或由业务域注册解析）：\n" + "\n".join(offenders)


def test_task_device_field_is_gone():
    """``Task.device`` 已由软引用取代：字段还在就说明方案 C 没落干净。"""
    from core.models import Task

    assert "device" not in {field.name for field in Task._meta.get_fields()}
    assert {"target_type", "target_id", "target_label"} <= {field.name for field in Task._meta.get_fields()}
