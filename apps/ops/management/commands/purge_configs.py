"""清理「配置解析产物」。

背景：配置**原文**只存在一份（Git 仓库），但**解析结果**写进了各资产表，而这些表与
``DeviceConfig`` 之间**没有任何外键**——所以删 ``DeviceConfig``、删仓库都不会级联清掉
它们，手工清又容易漏。本命令把「哪些行来自配置解析」集中到一处，并且默认只报告。

「配置解析产物」用 ``ConfigBase.__subclasses__()`` 运行时枚举（当前 24 个模型），
这个定义是自维护的：新增 Saver 或模型会自动纳入。实测 Saver 代码里写的模型全部都是
``ConfigBase`` 子类，所以不存在"配了 Saver 但不属于 ConfigBase"的漏网之鱼。

用法::

    manage.py purge_configs --device sw-bj-01                  # 只报告（默认 dry-run）
    manage.py purge_configs --device sw-bj-01 --yes            # 真正删除
    manage.py purge_configs --all --yes --with-workflow        # 连 Task/Stage 一起清
    manage.py purge_configs --all --yes --purge-repo           # 连 Git 仓库一起删

边界（报告里也会逐条列出）：

- ``--with-workflow`` 默认关闭：Task/Stage 是工作流历史，但 ``Stage.output_data`` 可能
  存着配置**全文**（``run_collection_stage`` 会写 ``{"config": ...}``），要清得显式加。
- ``--purge-repo`` 删的是**整个**仓库，所以强制要求 ``--all``；Git 历史里的原文不做重写。
- 人工 / Excel / 运行态采集的数据**不会动**。注意 ``Route`` / ``Vrf`` 同时也是运行态采集
  接口（``/api/trace/route-collect*``）的落点，与配置解析产物共用一张表，按表清无法区分来源。
- 堆叠组：备机不持有配置，产物记在**主设备**名下，所以 ``--device <备机>`` 会自动折算到主设备。
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assets.models import ConfigBase, Device, DeviceConfig
from ops.config_owner import resolve_config_owner
from ops.models import InternetAnalysis

logger = logging.getLogger(__name__)

WORKER_HINT = "建议先 `docker compose stop worker`：解析/采集任务可能在你删除的过程中并发写回。"


class Command(BaseCommand):
    help = "清理某台（或全部）设备由配置解析出来的数据与 DeviceConfig 记录（默认只报告，加 --yes 才删）"

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--device",
            action="append",
            metavar="HOSTNAME",
            help="设备主机名，可重复；堆叠组会折算到配置属主",
        )
        target.add_argument("--all", action="store_true", help="所有设备")
        parser.add_argument("--yes", action="store_true", help="真正执行删除（默认只做 dry-run）")
        parser.add_argument(
            "--with-workflow",
            action="store_true",
            help="连 Task/Stage 一起清（Stage.output_data 里可能存着配置原文）",
        )
        parser.add_argument(
            "--purge-repo",
            action="store_true",
            help="连 Git 配置仓库一起删；会清掉所有设备的原文，因此必须与 --all 同用",
        )

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        if options["purge_repo"] and not options["all"]:
            raise CommandError("--purge-repo 会删掉整个仓库（所有设备的原文），只能与 --all 同用")

        owners = self._resolve_owners(options)
        owner_ids = [device.pk for device in owners]
        dry_run = not options["yes"]

        self.stdout.write(f"配置属主（{len(owners)} 台）: " + ", ".join(device.hostname for device in owners))
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run：只统计不删除，确认后再加 --yes"))
        else:
            self.stdout.write(self.style.WARNING(WORKER_HINT))

        groups = self._collect(owner_ids, options["with_workflow"])
        plan = self._print_plan(groups)
        self._print_repo(options["purge_repo"])
        self._print_kept(options["with_workflow"])

        if dry_run:
            return

        # 数据库删除放在一个事务里；文件系统删除不能回滚，放到事务提交之后
        deleted_total = 0
        with transaction.atomic():
            for _label, rows in plan:
                for model, queryset in rows:
                    deleted, _detail = queryset.delete()
                    deleted_total += deleted
                    self.stdout.write(f"  已删除 {model.__name__}: {deleted} 行")

        if options["purge_repo"]:
            self._purge_repo()

        self.stdout.write(self.style.SUCCESS(f"完成：共删除 {deleted_total} 行"))

    # ------------------------------------------------------------------
    # 目标解析
    # ------------------------------------------------------------------

    def _resolve_owners(self, options) -> list[Device]:
        """把 --device / --all 折算成「配置属主」并按 pk 去重（备机的产物记在主设备名下）。"""
        if options["all"]:
            devices = list(Device.objects.order_by("pk"))
        else:
            names: list[str] = options["device"]
            found = {device.hostname: device for device in Device.objects.filter(hostname__in=names)}
            missing = [name for name in names if name not in found]
            if missing:
                raise CommandError("设备不存在: " + ", ".join(missing))
            devices = [found[name] for name in names]

        owners: dict[int, Device] = {}
        for device in devices:
            owner = resolve_config_owner(device)
            if owner.pk != device.pk:
                self.stdout.write(f"{device.hostname} 属于堆叠组，配置归属主设备 {owner.hostname}")
            owners.setdefault(owner.pk, owner)
        return list(owners.values())

    def _config_models(self):
        """配置解析产物 = ConfigBase 的全部子类（运行时枚举，新增模型自动纳入）。"""
        return sorted(ConfigBase.__subclasses__(), key=lambda model: model.__name__)

    def _collect(self, owner_ids: list[int], with_workflow: bool) -> list[tuple[str, list[tuple[Any, Any]]]]:
        from core.models import Stage, Task

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
                [(InternetAnalysis, InternetAnalysis.objects.filter(device_id__in=owner_ids))],
            ),
        ]
        if with_workflow:
            # Stage 写在前面：先删干净，Task 删除时就没有级联可走，两边报数才准确
            groups.append(
                (
                    "工作流记录（Stage 先删，Task 再删）",
                    [
                        (Stage, Stage.objects.filter(task__device_id__in=owner_ids)),
                        (Task, Task.objects.filter(device_id__in=owner_ids)),
                    ],
                )
            )
        return groups

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def _print_plan(self, groups) -> list[tuple[str, list[tuple[Any, Any]]]]:
        self.stdout.write("")
        self.stdout.write("将删除：")
        plan: list[tuple[str, list[tuple[Any, Any]]]] = []
        total = 0
        for label, rows in groups:
            present = [(model, queryset, queryset.count()) for model, queryset in rows]
            present = [(model, queryset, count) for model, queryset, count in present if count]
            plan.append((label, [(model, queryset) for model, queryset, _count in present]))
            self.stdout.write(f"  {label}")
            if not present:
                self.stdout.write("    （无）")
                continue
            for model, _queryset, count in present:
                total += count
                self.stdout.write(f"    {model.__name__:<18} {count}")
        self.stdout.write(f"  合计 {total} 行")
        return plan

    def _repo_path(self) -> Path:
        # 延迟导入：测试里可以替换 ops.config_repo.CONFIG_REPO_PATH
        from ops.config_repo import CONFIG_REPO_PATH

        return Path(CONFIG_REPO_PATH)

    def _print_repo(self, purge_repo: bool) -> None:
        self.stdout.write("")
        path = self._repo_path()
        if not purge_repo:
            self.stdout.write(f"Git 仓库未清理（加 --purge-repo）: {path}")
            return
        if not path.exists():
            self.stdout.write(f"Git 仓库: {path}（不存在）")
            return
        files = sum(1 for item in path.rglob("*") if item.is_file())
        self.stdout.write(f"Git 仓库将删除: {path}（含 .git 共 {files} 个文件）")
        self.stdout.write("  注意：只删本环境这一个目录，Git 历史里的原文不做重写；")
        self.stdout.write("        宿主机与 app_data 卷里可能各有一份，要分别处理。")

    def _print_kept(self, with_workflow: bool) -> None:
        from core.models import Stage, Task

        config_set = set(self._config_models()) | {DeviceConfig, InternetAnalysis}
        self.stdout.write("")
        self.stdout.write("不会动（人工 / Excel 数据，全库计数）：")
        shown = False
        for model in django_apps.get_app_config("assets").get_models():
            if model in config_set:
                continue
            count = model.objects.count()
            if count:
                shown = True
                self.stdout.write(f"    {model.__name__:<18} {count}")
        if not shown:
            self.stdout.write("    （无）")

        self.stdout.write("  注意：Route / Vrf 与配置解析产物共用同一张表，运行态采集接口")
        self.stdout.write("        （/api/trace/route-collect*）写进去的行也会被一起清掉。")

        if not with_workflow:
            stages = Stage.objects.count()
            tasks = Task.objects.count()
            if stages or tasks:
                self.stdout.write("")
                self.stdout.write(f"Task/Stage 未清理（加 --with-workflow）: Task {tasks} 行 / Stage {stages} 行")
                self.stdout.write("  其中 Stage.output_data 可能存着配置原文。")

    def _purge_repo(self) -> None:
        path = self._repo_path()
        if path.exists():
            shutil.rmtree(path)
            self.stdout.write(f"  已删除 Git 仓库目录: {path}（下次写入配置时会自动重建）")
