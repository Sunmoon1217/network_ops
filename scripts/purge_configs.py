"""清理「配置解析产物」——独立运维脚本（原 manage.py purge_configs）。

    uv run python scripts/purge_configs.py --device sw-bj-01            # 只报告（默认 dry-run）
    uv run python scripts/purge_configs.py --device sw-bj-01 --yes      # 真正删除
    uv run python scripts/purge_configs.py --all --yes --purge-repo     # 连 Git 仓库一起删

放在 scripts/ 是为了脱离业务域依赖矩阵（一次跨四个域的表）。背景与取舍见 handbook/ingest.md。
退出码：0 正常；2 参数错误。
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, TextIO

WORKER_HINT = "建议先 `docker compose stop worker`：解析/采集任务可能在你删除的过程中并发写回。"

logger = logging.getLogger(__name__)


class PurgeError(Exception):
    """参数或环境问题：打印后以退出码 2 结束。"""


def _setup_django() -> None:
    """把项目根塞进 sys.path 再 django.setup()（直接跑脚本时 sys.path[0] 是 scripts/）。"""
    import os

    import django

    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netops.settings")
    django.setup()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="purge_configs.py",
        description="清理某台（或全部）设备由配置解析出来的数据与 DeviceConfig 记录（默认只报告，加 --yes 才删）",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--device", action="append", metavar="HOSTNAME", help="设备主机名，可重复；堆叠组会折算到配置属主")
    target.add_argument("--all", action="store_true", help="所有设备")
    parser.add_argument("--yes", action="store_true", help="真正执行删除（默认只做 dry-run）")
    parser.add_argument("--with-workflow", action="store_true", help="连 Task/Stage 一起清（Stage.output_data 里可能存着配置原文）")
    parser.add_argument(
        "--purge-repo",
        action="store_true",
        help="连 Git 配置仓库一起删；会清掉所有设备的原文，因此必须与 --all 同用",
    )
    return parser


class _Purge:
    """一次清理的全部动作；``out`` 注入是为了测试能抓输出。"""

    def __init__(self, out: TextIO) -> None:
        self.out = out

    def write(self, message: str = "") -> None:
        self.out.write(message + "\n")

    # —— 参数解析 ——

    def _resolve_owners(self, args: argparse.Namespace) -> list[Any]:
        """把 --device / --all 折算成「配置属主」并按 pk 去重（备机的产物记在主设备名下）。"""
        from assets.models import Device
        from configs.config_owner import resolve_config_owner

        if args.all:
            devices = list(Device.objects.order_by("pk"))
        else:
            names: list[str] = args.device
            found = {device.hostname: device for device in Device.objects.filter(hostname__in=names)}
            missing = [name for name in names if name not in found]
            if missing:
                raise PurgeError("设备不存在: " + ", ".join(missing))
            devices = [found[name] for name in names]

        owners: dict[int, Any] = {}
        for device in devices:
            owner = resolve_config_owner(device)
            if owner.pk != device.pk:
                self.write(f"{device.hostname} 属于堆叠组，配置归属主设备 {owner.hostname}")
            owners.setdefault(owner.pk, owner)
        return list(owners.values())

    def _config_models(self) -> list[Any]:
        """配置解析产物 = ConfigBase 的全部子类（运行时枚举，新增模型自动纳入）。"""
        from configs.models import ConfigBase

        return sorted(ConfigBase.__subclasses__(), key=lambda model: model.__name__)

    def _access_flow_q(self, owner_ids: list[int]):
        """AccessFlow 的按设备过滤：contexts 里挂着任一目标设备的行。

        它是跨设备聚合行、没有 device 字段，只能走 ``device_ids``（jsonb 数组）的
        包含过滤，命中 GIN 索引。空列表必须显式给「查不到任何行」的条件——
        ``Q()`` 是恒真，会把全表都算进来。
        """
        from django.db.models import Q

        if not owner_ids:
            return Q(pk__in=[])
        query = Q()
        for pk in owner_ids:
            query |= Q(device_ids__contains=[pk])
        return query

    def _collect(self, owner_ids: list[int], with_workflow: bool) -> list[tuple[str, list[tuple[Any, Any]]]]:
        from analysis.models import AccessFlow, InternetAnalysis
        from configs.models import DeviceConfig

        groups: list[tuple[str, list[tuple[Any, Any]]]] = [
            (
                "配置解析产物（ConfigBase 的全部子类）",
                [(model, model.objects.filter(device_id__in=owner_ids)) for model in self._config_models()],
            ),
            (
                "配置记录（原文在 Git 仓库里，这里只是索引）",
                [(DeviceConfig, DeviceConfig.objects.filter(device_id__in=owner_ids))],
            ),
            (
                "派生缓存（由上面的表算出，必须跟着清）",
                [
                    (InternetAnalysis, InternetAnalysis.objects.filter(device_id__in=owner_ids)),
                    # AccessFlow 是跨设备聚合行（没有归属设备字段），只要 contexts 里
                    # 还挂着目标设备的行就都算它的产物，按 GIN 索引走 jsonb 包含过滤
                    (AccessFlow, AccessFlow.objects.filter(self._access_flow_q(owner_ids)).distinct()),
                ],
            ),
        ]
        if with_workflow:
            from core.models import Stage, Task

            # Stage 写在前面：先删干净，Task 删除时就没有级联可走，两边报数才准确
            groups.append(
                (
                    "工作流记录（Stage 先删，Task 再删）",
                    [
                        (Stage, Stage.objects.filter(task__target_type="device", task__target_id__in=owner_ids)),
                        (Task, Task.objects.filter(target_type="device", target_id__in=owner_ids)),
                    ],
                )
            )
        return groups

    def _print_plan(self, groups) -> list[tuple[str, list[tuple[Any, Any]]]]:
        self.write("")
        self.write("将删除：")
        plan: list[tuple[str, list[tuple[Any, Any]]]] = []
        total = 0
        for label, rows in groups:
            present = [(model, queryset, queryset.count()) for model, queryset in rows]
            present = [(model, queryset, count) for model, queryset, count in present if count]
            plan.append((label, [(model, queryset) for model, queryset, _count in present]))
            self.write(f"  {label}")
            if not present:
                self.write("    （无）")
                continue
            for model, _queryset, count in present:
                total += count
                self.write(f"    {model.__name__:<18} {count}")
        self.write(f"  合计 {total} 行")
        return plan

    def _repo_path(self) -> Path:
        # 路径的唯一来源是 settings（env CONFIG_REPO_PATH）；测试用 override_settings 换目录
        from django.conf import settings

        return Path(settings.CONFIG_REPO_PATH)

    def _print_repo(self, purge_repo: bool) -> None:
        self.write("")
        path = self._repo_path()
        if not purge_repo:
            self.write(f"Git 仓库未清理（加 --purge-repo）: {path}")
            return
        if not path.exists():
            self.write(f"Git 仓库: {path}（不存在）")
            return
        files = sum(1 for item in path.rglob("*") if item.is_file())
        self.write(f"Git 仓库将删除: {path}（含 .git 共 {files} 个文件）")
        self.write("  注意：只删本环境这一个目录，Git 历史里的原文不做重写；")
        self.write("        路径取自 CONFIG_REPO_PATH（容器里是命名卷 config_repo_data 的挂载点，")
        self.write("        宿主机直跑时是 <项目根>/data/config_repo）——两边各一份，互不影响。")

    def _print_kept(self, with_workflow: bool) -> None:
        from django.apps import apps as django_apps

        from analysis.models import InternetAnalysis
        from configs.models import DeviceConfig

        config_set = set(self._config_models()) | {DeviceConfig, InternetAnalysis}
        self.write("")
        self.write("不会动（人工 / Excel 数据，全库计数）：")
        shown = False
        # django-stubs 把 get_models() 标成 list[type[Model]]，而「type[Model]」这种写法下
        # 看不到模型管理器 `.objects`（只有具体模型类才有），这里放宽成 Any。
        asset_models: list[Any] = list(django_apps.get_app_config("assets").get_models())
        for model in asset_models:
            if model in config_set:
                continue
            count = model.objects.count()
            if count:
                shown = True
                self.write(f"    {model.__name__:<18} {count}")
        if not shown:
            self.write("    （无）")

        self.write("  注意：Route / Vrf 与配置解析产物共用同一张表，运行态采集接口")
        self.write("        （/api/analysis/trace/route-collect*）写进去的行也会被一起清掉。")

        if not with_workflow:
            from core.models import Stage, Task

            stages = Stage.objects.count()
            tasks = Task.objects.count()
            if stages or tasks:
                self.write("")
                self.write(f"Task/Stage 未清理（加 --with-workflow）: Task {tasks} 行 / Stage {stages} 行")
                self.write("  其中 Stage.output_data 可能存着配置原文。")

    def _purge_repo(self) -> None:
        path = self._repo_path()
        if path.exists():
            shutil.rmtree(path)
            self.write(f"  已删除 Git 仓库目录: {path}（下次写入配置时会自动重建）")

    # —— 主流程 ——

    def run(self, args: argparse.Namespace) -> int:
        from django.db import transaction

        if args.purge_repo and not args.all:
            raise PurgeError("--purge-repo 会删掉整个仓库（所有设备的原文），只能与 --all 同用")

        owners = self._resolve_owners(args)
        owner_ids = [device.pk for device in owners]
        dry_run = not args.yes

        self.write(f"配置属主（{len(owners)} 台）: " + ", ".join(device.hostname for device in owners))
        self.write("dry-run：只统计不删除，确认后再加 --yes" if dry_run else WORKER_HINT)

        groups = self._collect(owner_ids, args.with_workflow)
        plan = self._print_plan(groups)
        self._print_repo(args.purge_repo)
        self._print_kept(args.with_workflow)

        if dry_run:
            return 0

        # 数据库删除放在一个事务里；文件系统删除不能回滚，放到事务提交之后
        deleted_total = 0
        with transaction.atomic():
            for _label, rows in plan:
                for model, queryset in rows:
                    deleted, _detail = queryset.delete()
                    deleted_total += deleted
                    self.write(f"  已删除 {model.__name__}: {deleted} 行")

        if args.purge_repo:
            self._purge_repo()

        self.write(f"完成：共删除 {deleted_total} 行")
        return 0


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    """入口：``argv`` 缺省取 ``sys.argv[1:]``，``out`` 缺省 stdout（测试注入 StringIO）。"""
    _setup_django()
    args = _parser().parse_args(argv)
    stream = out if out is not None else sys.stdout
    try:
        return _Purge(stream).run(args)
    except PurgeError as exc:
        stream.write(f"错误：{exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
