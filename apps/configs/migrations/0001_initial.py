"""configs 初始迁移：Vlan 从 assets 迁入（state 挂载 + RENAME 表名）。

范本是 ``analysis/0002_accessflow``：**不重建表、不丢数据**。

- ``assets/0036_remove_vlan_state`` 只从迁移状态删除模型（database_operations 为空），
  表原样保留；
- 本迁移在 state 层建出 ``configs.Vlan``（字段/约束照抄 0023 之后的终态），
  DB 层只执行一次 ``RENAME``——表名对齐新 app，数据随表走。

``dependencies`` 必须显式指向 ``assets/0036``：``Vlan.device`` 是到 ``assets.Device``
的跨 app 外键，fresh 库从零 migrate 时要保证目标表先建出来（存量库不受影响，但两条
路径必须能走同一条链，见设计稿 §迁移手法）。

索引与约束名：``uni_vlan_device_vid`` 不含 app 名，随表走不需要改；
``devices_vlan_pkey`` / ``devices_vlan_vid_check`` 是更早表名（``devices_vlan``）时代
留下的历史命名，``assets_vlan_device_id_*`` 是 FK 自动索引——RENAME 不改它们，
Django 也不按其名字做状态比较，功能无影响，故原样保留。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0036_remove_vlan_state"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Vlan",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        (
                            "device",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                to="assets.device",
                                verbose_name="关联设备",
                            ),
                        ),
                        ("is_active", models.BooleanField(default=True, verbose_name="是否生效")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                        ("vid", models.PositiveIntegerField(verbose_name="VLAN ID")),
                        ("name", models.CharField(blank=True, default="", max_length=100, verbose_name="VLAN名称")),
                        ("description", models.CharField(blank=True, default="", max_length=255, verbose_name="描述")),
                    ],
                    options={
                        "verbose_name": "VLAN",
                        "verbose_name_plural": "VLAN",
                        "ordering": ("vid",),
                        "constraints": [
                            models.UniqueConstraint(fields=("device", "vid"), name="uni_vlan_device_vid"),
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        # Django 没有 RenameTable 迁移操作，用原生 RENAME（带反向，数据全程随表走）。
        migrations.RunSQL(
            sql="ALTER TABLE assets_vlan RENAME TO configs_vlan",
            reverse_sql="ALTER TABLE configs_vlan RENAME TO assets_vlan",
        ),
    ]
