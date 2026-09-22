"""互联网资产分析缓存表从 ops（label=operator）迁入 analysis。

**不重建表、不丢数据**：表 ``operator_internetanalysis`` 由 ``operator.0001`` 建出，
已部署的库里已有行。这里分两步走：

- ``operator.0003`` 只从**迁移状态**里删除该模型（database_operations 为空），
  数据库里的表原样保留；
- 本迁移在 state 层建出 ``analysis.InternetAnalysis``，DB 层只执行一次
  ``RENAME``——表名对齐新 app，数据随表走。

顺序由 dependencies 保证；测试库从零构建与已有库升级走的是同一条路径。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('assets', '0025_service_unique_per_device'),
        ('operator', '0003_remove_internet_analysis_state'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='InternetAnalysis',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('result', models.JSONField(default=dict, verbose_name='分析结果')),
                        ('analyzed_at', models.DateTimeField(auto_now=True, verbose_name='分析时间')),
                        ('duration_ms', models.PositiveIntegerField(default=0, verbose_name='分析耗时(毫秒)')),
                        ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='internet_analyses', to='assets.device', verbose_name='GSLB 设备')),
                    ],
                    options={
                        'verbose_name': '互联网资产分析缓存',
                        'verbose_name_plural': '互联网资产分析缓存',
                        'ordering': ('-analyzed_at', '-pk'),
                        'constraints': [models.UniqueConstraint(fields=('device',), name='uni_internet_analysis_device')],
                    },
                ),
            ],
            database_operations=[],
        ),
        # 表改名对齐新 app：Django 没有 RenameTable 迁移操作，用原生 RENAME（带反向，
        # `migrate analysis 0001` 回滚时表名先改回去，数据全程随表走）。
        migrations.RunSQL(
            sql="ALTER TABLE operator_internetanalysis RENAME TO analysis_internetanalysis",
            reverse_sql="ALTER TABLE analysis_internetanalysis RENAME TO operator_internetanalysis",
        ),
    ]
