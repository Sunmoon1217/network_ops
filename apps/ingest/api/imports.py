"""Excel 导入的两个接口：上传分发 + 模板下载。

读的 ``IMPORT_SHEETS`` 在 ``device_import.py``，两者必须同域；路由见 handbook/api.md。
"""

import logging
from typing import cast

from django.http import HttpResponse
from openpyxl.worksheet.worksheet import Worksheet
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ingest.device_import import IMPORT_SHEETS

logger = logging.getLogger(__name__)


@api_view(["POST"])
def import_excel(request):
    """导入 Excel 文件，支持多个 Sheet"""
    from openpyxl import load_workbook

    excel_file = request.FILES.get("file")
    if not excel_file:
        return Response({"error": "请上传 Excel 文件"}, status=400)

    try:
        wb = load_workbook(excel_file, read_only=True, data_only=True)
    except Exception as e:
        return Response({"error": f"文件格式错误: {e}"}, status=400)

    results = {}
    # Sheet 清单 / 列头 / 导入函数的唯一来源是模块级 IMPORT_SHEETS（定义在各 _import_* 之后，
    # 运行期才查名字，此处直接引用即可）——模板下载接口读同一份表，两者不可能漂移。

    for sheet_name, spec in IMPORT_SHEETS.items():
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            try:
                results[sheet_name] = spec["importer"](ws)
            except Exception as e:
                logger.error("导入 %s 失败: %s", sheet_name, e)
                results[sheet_name] = {"created": 0, "updated": 0, "errors": [str(e)]}
        else:
            results[sheet_name] = {"created": 0, "updated": 0, "errors": [], "skipped": True}

    wb.close()
    return Response({"success": True, "results": results})


@api_view(["GET"])
def import_template(request):
    """下载导入模板（xlsx）：每个 Sheet 一行列头，列头取自 IMPORT_SHEETS。

    只写表头、**不放示例行**——示例行留在模板里，用户忘了删就会被当成数据导进来。
    """
    from io import BytesIO
    from urllib.parse import quote

    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    if ws:
        wb.remove(ws)
    for sheet_name, spec in IMPORT_SHEETS.items():
        ws = wb.create_sheet(title=sheet_name)
        ws.append(spec["headers"])
        # 中文按两个字符宽估，够看清表头即可
        for idx, header in enumerate(spec["headers"], start=1):
            cast(Worksheet, ws).column_dimensions[get_column_letter(idx)].width = len(header) * 2 + 4

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote('设备导入模板.xlsx')}"
    return response
