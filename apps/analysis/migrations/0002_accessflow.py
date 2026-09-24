"""AccessFlow 从 ingest（label=operator）迁入 analysis：state 挂载 + RENAME 表名。

与 0001（InternetAnalysis 迁入）同一手法，**不重建表、不丢数据**：

- ``operator.0005`` 只从迁移状态删除模型（database_operations 为空），表原样保留；
- 本迁移在 state 层建出 ``analysis.AccessFlow``（字段/约束/索引照抄 0004 之后的
  终态），DB 层只执行一次 ``RENAME``——表名对齐新 app，数据与 GIN 索引随表走
  （索引名 ``gin_accessflow_*``、约束名 ``uni_accessflow_action_key`` 不含 app 名，
  不需要改）。

fresh 库（从零 migrate）与存量库升级走的是同一条路径：operator.0002 建表 →
operator.0004 加 action → operator.0005 摘 state → 本迁移 RENAME。
"""

import django.contrib.postgres.indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operator", "0005_remove_accessflow_state"),
        ("analysis", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AccessFlow",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("src_ip", models.GenericIPAddressField(verbose_name="源地址")),
                        ("src_prefix", models.PositiveSmallIntegerField(verbose_name="源前缀长度")),
                        ("src_range_end", models.CharField(blank=True, default="", max_length=45, verbose_name="源结束地址")),
                        ("dst_ip", models.GenericIPAddressField(verbose_name="目的地址")),
                        ("dst_prefix", models.PositiveSmallIntegerField(verbose_name="目的前缀长度")),
                        ("dst_range_end", models.CharField(blank=True, default="", max_length=45, verbose_name="目的结束地址")),
                        ("protocol", models.CharField(choices=[("tcp", "TCP"), ("udp", "UDP"), ("tcp-udp", "TCP/UDP"), ("icmp", "ICMP"), ("any", "ANY")], max_length=10, verbose_name="协议")),
                        ("port", models.CharField(blank=True, default="", max_length=15, verbose_name="起始端口")),
                        ("port2", models.CharField(blank=True, default="", max_length=15, verbose_name="结束端口")),
                        ("action", models.CharField(choices=[("allow", "放行"), ("deny", "拒绝")], max_length=10, verbose_name="动作")),
                        ("contexts", models.JSONField(default=dict, verbose_name="命中上下文")),
                        ("device_ids", models.JSONField(default=list, verbose_name="设备ID列表")),
                        ("policy_ids", models.JSONField(default=list, verbose_name="策略ID列表")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                    ],
                    options={
                        "verbose_name": "访问流",
                        "verbose_name_plural": "访问流",
                        "ordering": ("-updated_at", "-pk"),
                        "indexes": [
                            django.contrib.postgres.indexes.GinIndex(fields=["device_ids"], name="gin_accessflow_device_ids"),
                            django.contrib.postgres.indexes.GinIndex(fields=["policy_ids"], name="gin_accessflow_policy_ids"),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                fields=[
                                    "src_ip",
                                    "src_prefix",
                                    "src_range_end",
                                    "dst_ip",
                                    "dst_prefix",
                                    "dst_range_end",
                                    "protocol",
                                    "port",
                                    "port2",
                                    "action",
                                ],
                                name="uni_accessflow_action_key",
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        # 表改名对齐新 app：Django 没有 RenameTable 迁移操作，用原生 RENAME（带反向，
        # `migrate analysis` 回滚时表名先改回去，数据全程随表走）。
        migrations.RunSQL(
            sql="ALTER TABLE operator_accessflow RENAME TO analysis_accessflow",
            reverse_sql="ALTER TABLE analysis_accessflow RENAME TO operator_accessflow",
        ),
    ]
