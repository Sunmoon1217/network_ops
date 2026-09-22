"""把 InternetAnalysis 的**迁移状态**移交 analysis app（真实见 analysis.0001）。

state 层删除模型、DB 层什么都不做：已部署库里的 operator_internetanalysis 表
必须原样留着，等 analysis.0001 的 RENAME 来接——先删表就丢数据了。
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # 线性化：主仓 0002_accessflow 已占用 0002，本迁移排其后（两个都依赖 0001 会分叉出多叶子）
        ('operator', '0002_accessflow'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name='InternetAnalysis')],
            database_operations=[],
        ),
    ]
