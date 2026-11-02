from django.conf import settings
from django.db import models


class Spreadsheet(models.Model):
    """通用表格工作簿（一份 xlsx 对应一条记录）。

    前后端唯一交换格式 ``data``（JSON）::

        {"sheets": [{"name": "Sheet1", "rows": [[单元格, ...], ...]}, ...]}

    - 单元格只能是 JSON 标量（str / int / float / bool / None）；
    - ``rows`` 的前 ``header_rows`` 行是表头行（多行表头），其余是数据行——
      ``header_rows`` 缺省 1（单行表头不落键）、上限见 ``docs.schema.MAX_HEADER_ROWS``；
    - 整张表就是一张矩形网格，语义由使用者自己定义；
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
    - ``changes``：相对上一版本的单元格级 diff（截断上限见 ``docs.diff.MAX_CHANGES``）；
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


class Document(models.Model):
    """一份已转换、待推送 / 已推送 Dify 知识库的文档。

    管道：上传（源文件 + 可选图片附件）→ 转换（``docs.convert``：无图 → md；
    含图 → 自包含 html；pdf 直传不转换）→ 落库留档 → 推送 Dify 知识库
    （``docs.dify``：``document/create-by-file``，一次一个文件）。

    - ``source_file`` 存上传的原文件（留档与 pdf 直传用）；``converted`` 存转换
      产物文本（md / html；pdf 直传时为空）——都在库里，不依赖媒体卷；
    - ``status``：``converted``（转换完成，待推送）/ ``pushed``（已推送）/
      ``push_failed``（推送失败，可重试，``error`` 记原因）；
      转换失败不落记录、直接在接口层返回 400；
    - ``dify_indexing_status`` 由 ``/status/`` 接口从 Dify 的 indexing-status
      同步（waiting / indexing / completed / error）。
    """

    STATUS_CONVERTED = "converted"
    STATUS_PUSHED = "pushed"
    STATUS_PUSH_FAILED = "push_failed"
    STATUS_CHOICES = [
        (STATUS_CONVERTED, "已转换待推送"),
        (STATUS_PUSHED, "已推送"),
        (STATUS_PUSH_FAILED, "推送失败"),
    ]

    name = models.CharField("文件名", max_length=255)
    source_format = models.CharField("源格式", max_length=16)  # txt/md/docx/html/pdf/xlsx/csv
    target_format = models.CharField("产物格式", max_length=8)  # md/html/pdf（pdf 直传）
    source_file = models.BinaryField("源文件")
    converted = models.TextField("转换产物", blank=True, default="")
    has_images = models.BooleanField("含图片", default=False)
    status = models.CharField("状态", max_length=16, choices=STATUS_CHOICES, default=STATUS_CONVERTED)
    error = models.TextField("错误信息", blank=True, default="")
    dify_document_id = models.CharField("Dify 文档 ID", max_length=64, blank=True, default="")
    dify_batch = models.CharField("Dify 批次号", max_length=64, blank=True, default="")
    dify_indexing_status = models.CharField("Dify 索引状态", max_length=32, blank=True, default="")
    pushed_at = models.DateTimeField("推送时间", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="创建人")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="最后操作人")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "文档"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name} ({self.status})"
