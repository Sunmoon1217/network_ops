"""Vlan 迁出 assets：**只从迁移状态删除模型，表与数据留在原地**。

与 ``analysis/0002_accessflow`` 同一手法的前半段（那里对应的是 ``operator.0005``）：

- 本迁移 ``database_operations`` 为空——`assets_vlan` 表原样保留；
- 表由 ``configs/0001_initial`` 在 DB 层 `RENAME` 接走，数据与约束随表走。

拆成两条迁移而不是一条，是为了让「摘 state」和「挂 state + 改名」各自可反向：
反向时先回滚 ``configs/0001``（表名改回去），再回滚本迁移（恢复 assets 的模型状态）。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0035_ci_object_link"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Vlan")],
            database_operations=[],
        ),
    ]
