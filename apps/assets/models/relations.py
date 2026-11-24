"""统一关系表（T3）：跨类型 CI 之间的直接关系。

两端存 ``ci_id`` 字符串而非外键（类型不绑死），只存最近一跳、不物化传递闭包。
约定与取舍见 handbook/assets.md「统一关系表」。
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

    两端存 ``ci_id`` 字符串，CI 删除后可能留孤儿行（现阶段靠录入校验兜）。
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
