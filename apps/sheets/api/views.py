"""通用表格（xlsx 编辑与历史）接口。

函数视图 + ``@api_view``（与 ``analysis/api`` 同风格）。权限走全局默认
``IsOperatorOrReadOnly``：读任何已认证用户可用，写（上传 / 保存 / 恢复 / 删除）限操作员。
"""

from pathlib import Path
from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from sheets.diff import ZERO_SUMMARY, diff_data, is_empty
from sheets.models import Spreadsheet, SpreadsheetRevision
from sheets.schema import DataError, normalize_data
from sheets.xlsx_io import build_xlsx, parse_xlsx

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# 序列化（响应形状的唯一来源；前后端字段对账见前端 types/spreadsheet.ts）
# ---------------------------------------------------------------------------


def _summary(sp: Spreadsheet) -> dict:
    return {
        "id": sp.id,
        "name": sp.name,
        "sheet_names": [str(s.get("name", "")) for s in (sp.data.get("sheets") or [])],
        "latest_revision": sp.latest_revision,
        "created_by": sp.created_by.username if sp.created_by else None,
        "updated_by": sp.updated_by.username if sp.updated_by else None,
        "created_at": sp.created_at,
        "updated_at": sp.updated_at,
    }


def _detail(sp: Spreadsheet) -> dict:
    return {**_summary(sp), "data": sp.data}


def _revision_summary(rev: SpreadsheetRevision) -> dict:
    return {
        "id": rev.id,
        "revision": rev.revision,
        "note": rev.note,
        "summary": rev.summary,
        "created_by": rev.created_by.username if rev.created_by else None,
        "created_at": rev.created_at,
    }


def _revision_detail(rev: SpreadsheetRevision) -> dict:
    return {**_revision_summary(rev), "changes": rev.changes, "data": rev.data}


def _save_result(created: bool, revision: int, changes: list, summary: dict) -> dict:
    return {"created": created, "revision": revision, "changes": changes, "summary": summary}


# ---------------------------------------------------------------------------
# 内部：落版本
# ---------------------------------------------------------------------------


def _apply_revision(sp: Spreadsheet, data: dict, note: str, user):
    """diff 后落一份新快照；无改动返回 ``(None, summary)``、不建版本（防历史刷屏）。"""
    changes, summary = diff_data(sp.data, data)
    if is_empty(summary):
        return None, summary
    with transaction.atomic():
        sp.data = data
        sp.updated_by = user
        sp.latest_revision += 1
        sp.save(update_fields=["data", "updated_by", "latest_revision", "updated_at"])
        rev = SpreadsheetRevision.objects.create(
            spreadsheet=sp,
            revision=sp.latest_revision,
            note=note,
            data=data,
            changes=changes,
            summary=summary,
            created_by=user,
        )
    return rev, summary


def _note(request) -> str:
    return str(request.data.get("note") or "").strip()[:200]


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@api_view(["GET"])
def spreadsheet_list(request):
    """工作簿列表（不含 data，列表页用）。"""
    return Response({"results": [_summary(sp) for sp in Spreadsheet.objects.all()]})


@api_view(["POST"])
def spreadsheet_upload(request):
    """上传 xlsx 建工作簿：解析成 data、落初始版本（v1「初始导入」）。"""
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "请上传 xlsx 文件"}, status=status.HTTP_400_BAD_REQUEST)
    if not str(f.name).lower().endswith(".xlsx"):
        return Response({"detail": "只支持 .xlsx 文件"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        data = normalize_data(parse_xlsx(f))
    except DataError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:  # openpyxl 的解析失败（损坏文件 / 伪装扩展名等）
        return Response({"detail": f"文件解析失败：{e}"}, status=status.HTTP_400_BAD_REQUEST)

    name = str(request.data.get("name") or Path(str(f.name)).stem or "未命名表格").strip()[:200]
    with transaction.atomic():
        sp = Spreadsheet.objects.create(name=name, data=data, latest_revision=1, created_by=request.user, updated_by=request.user)
        SpreadsheetRevision.objects.create(
            spreadsheet=sp,
            revision=1,
            note="初始导入",
            data=data,
            changes=[],
            summary={**ZERO_SUMMARY, "sheets_added": len(data["sheets"]), "truncated": False},
            created_by=request.user,
        )
    return Response(_detail(sp), status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "DELETE"])
def spreadsheet_detail(request, pk):
    """工作簿详情 / 保存编辑 / 删除。"""
    sp = get_object_or_404(Spreadsheet, pk=pk)
    if request.method == "GET":
        return Response(_detail(sp))
    if request.method == "DELETE":
        sp.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        data = normalize_data(request.data.get("data"))
    except DataError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    try:
        rev, summary = _apply_revision(sp, data, _note(request), request.user)
    except IntegrityError:
        return Response({"detail": "保存冲突：其他会话刚保存过，请刷新后重试"}, status=status.HTTP_409_CONFLICT)
    if rev is None:
        return Response(_save_result(False, sp.latest_revision, [], summary))
    return Response(_save_result(True, rev.revision, rev.changes, rev.summary), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def spreadsheet_export(request, pk):
    """导出 xlsx（默认当前版本；`?revision=N` 导出历史版本）。"""
    sp = get_object_or_404(Spreadsheet, pk=pk)
    data, filename = sp.data, f"{sp.name}.xlsx"
    rev_param = request.query_params.get("revision")
    if rev_param is not None:
        try:
            rev_no = int(rev_param)
        except ValueError:
            return Response({"detail": "revision 必须是整数"}, status=status.HTTP_400_BAD_REQUEST)
        rev = get_object_or_404(SpreadsheetRevision, spreadsheet=sp, revision=rev_no)
        data, filename = rev.data, f"{sp.name}-v{rev.revision}.xlsx"
    response = HttpResponse(build_xlsx(data), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@api_view(["GET"])
def revision_list(request, pk):
    """修改历史列表（新版本在前）。"""
    sp = get_object_or_404(Spreadsheet, pk=pk)
    return Response({"results": [_revision_summary(rev) for rev in sp.revisions.all()]})


@api_view(["GET"])
def revision_detail(request, pk, revision):
    """单个历史版本：全量快照 + 相对上一版本的变更明细。"""
    sp = get_object_or_404(Spreadsheet, pk=pk)
    rev = get_object_or_404(SpreadsheetRevision, spreadsheet=sp, revision=revision)
    return Response(_revision_detail(rev))


@api_view(["POST"])
def revision_restore(request, pk, revision):
    """回滚到指定历史版本（以一次新保存落地，历史不被改写）。"""
    sp = get_object_or_404(Spreadsheet, pk=pk)
    target = get_object_or_404(SpreadsheetRevision, spreadsheet=sp, revision=revision)
    note = _note(request) or f"恢复到版本 {target.revision}"
    try:
        rev, summary = _apply_revision(sp, target.data, note, request.user)
    except IntegrityError:
        return Response({"detail": "保存冲突：其他会话刚保存过，请刷新后重试"}, status=status.HTTP_409_CONFLICT)
    if rev is None:
        return Response(_save_result(False, sp.latest_revision, [], summary))
    return Response(_save_result(True, rev.revision, rev.changes, rev.summary), status=status.HTTP_201_CREATED)
