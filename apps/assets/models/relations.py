"""统一关系表（T3）：跨类型 CI 关系的登记与查询。

蓝图要求「只存 ci_id + 关系类型」：两端用 ``ConfigurationItem.ci_id`` 字符串而不是外键，
因为关系两端可以是任意 CI 类型（含 T4 才接入统一 CI 的现有资产模型），用 FK 会把类型绑死；
引用完整性由序列化器在录入时校验存在性，不在数据库层建强约束。

**上级归属只存最近一跳**：表里只登记直接关系，不物化传递闭包——
VM ``runs_on`` 物理机、物理机 ``located_in`` 机柜，就只存这两条，
不额外存 VM ``located_in`` 机柜。多跳遍历是 T7 关系图谱的事，
别在这里加 ``depth`` / ``path`` 之类的字段。

现有模型之间的专用外键 / M2M 全部保留为强约束，本表只补跨类型的弱关联，不替代它们。
"""

from django.db import models


class CIRelationType:
    """六类跨类型关系（字符串常量，不用 ``Enum``——同值字符串与 Enum 成员哈希不同）。"""

    RUNS_ON = "runs_on"
    DEPENDS_ON = "depends_on"
    DEPLOYED_ON = "deployed_on"
    CONNECTED_TO = "connected_to"
    LOCATED_IN = "located_in"
    MEMBER_OF = "member_of"


CI_RELATION_CHOICES = (
    (CIRelationType.RUNS_ON, "运行于"),
    (CIRelationType.DEPENDS_ON, "依赖于"),
    (CIRelationType.DEPLOYED_ON, "部署于"),
    (CIRelationType.CONNECTED_TO, "连接至"),
    (CIRelationType.LOCATED_IN, "位于"),
    (CIRelationType.MEMBER_OF, "属于"),
)


class CIRelationship(models.Model):
    """一条直接关系：``src --[relation_type]--> dst``。

    两端存 ``ci_id`` 字符串而非 FK，所以 CI 被删除后这里会留孤儿行；
    现阶段靠录入校验减少脏数据，批量清理命令等 T4 接入现有模型后再补。
    刻意不继承 ``ConfigBase``：关系登记是人工维护的台账，不能被 ``purge_configs`` 清掉。
    """

    src_ci_id = models.CharField(max_length=64, verbose_name="源 CI 标识")
    dst_ci_id = models.CharField(max_length=64, verbose_name="目标 CI 标识")
    relation_type = models.CharField(max_length=32, choices=CI_RELATION_CHOICES, verbose_name="关系类型")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "CI 关系"
        verbose_name_plural = verbose_name
        ordering = ("src_ci_id", "relation_type", "dst_ci_id")
        constraints = (
            models.UniqueConstraint(fields=["src_ci_id", "dst_ci_id", "relation_type"], name="uni_ci_relation_src_dst_type"),
            models.CheckConstraint(condition=~models.Q(src_ci_id=models.F("dst_ci_id")), name="ck_ci_relation_no_self_loop"),
        )
        indexes = (
            models.Index(fields=["src_ci_id", "relation_type"], name="ci_rel_src_type_idx"),
            models.Index(fields=["dst_ci_id", "relation_type"], name="ci_rel_dst_type_idx"),
        )

    def __str__(self):
        return f"{self.src_ci_id} -[{self.relation_type}]-> {self.dst_ci_id}"
