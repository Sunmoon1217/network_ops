"""AccessFlow 迁出 ingest（label=operator）：只从迁移状态摘除，**不动数据库**。

模型整体迁往 analysis（见 analysis.0002_accessflow：state 层挂载 + RENAME 表名，
数据随表走）。这里若写 RemoveModel 的 database_operations 会 DROP TABLE——所以用
SeparateDatabaseAndState 把「状态删除」与「数据库操作」分开，DB 层什么都不做；
表的去向由 analysis 侧的迁移负责。历史迁移 0002/0004 留在原地，别改写。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("operator", "0004_accessflow_action_key"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="AccessFlow")],
            database_operations=[],
        ),
    ]
