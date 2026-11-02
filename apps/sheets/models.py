from django.conf import settings
from django.db import models


class Spreadsheet(models.Model):
    """通用表格工作簿（一份 xlsx 对应一条记录）。

    前后端唯一交换格式 ``data``（JSON）::

        {"sheets": [{"name": "Sheet1", "rows": [[单元格, ...], ...]}, ...]}

    - 单元格只能是 JSON 标量（str / int / float / bool / None）；
    - ``rows`` 的第 1 行即表头行，整张表就是一张矩形网格，语义由使用者自己定义；
    - 当前状态存这里；每次保存在 :class:`SpreadsheetRevision` 落一份全量快照
      + 单元格级 diff（修改历史与回滚都基于快照，导出历史版本也直接读快照）。
    """

    name = models.CharField("名称", max_length=200)
    data = models.JSONField("当前数据", default=dict)
    latest_revision = models.PositiveIntegerField("最新版本号", default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="创建人")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="最后修改人")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "表格工作簿"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name} (v{self.latest_revision})"


class SpreadsheetRevision(models.Model):
    """工作簿的一次保存快照（修改历史）。

    - ``revision``：工作簿内自增版本号（上传导入是 1，之后每次保存 +1，恢复也 +1）；
    - ``data``：该版本的全量快照——历史查看、导出历史版本、回滚都不再依赖前一版本；
    - ``changes``：相对上一版本的单元格级 diff（截断上限见 ``sheets.diff.MAX_CHANGES``）；
    - ``summary``：变更计数（cells_changed / rows_added / rows_removed / sheets_added /
      sheets_removed / truncated），供历史列表直接展示。
    """

    spreadsheet = models.ForeignKey(Spreadsheet, on_delete=models.CASCADE, related_name="revisions", verbose_name="工作簿")
    revision = models.PositiveIntegerField("版本号")
    note = models.CharField("变更说明", max_length=200, blank=True, default="")
    data = models.JSONField("快照数据", default=dict)
    changes = models.JSONField("变更明细", default=list)
    summary = models.JSONField("变更计数", default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="操作人")
    created_at = models.DateTimeField("保存时间", auto_now_add=True)

    class Meta:
        ordering = ["-revision"]
        constraints = [models.UniqueConstraint(fields=["spreadsheet", "revision"], name="uniq_spreadsheet_revision")]
        verbose_name = "表格版本"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.spreadsheet_id} v{self.revision}"
