"""Vlan / SnmpConfig / Route 改为继承 ConfigBase。

三者原本都是裸 models.Model，各自重复实现了 device 字段，且都缺少 ConfigBase
提供的 is_active / created_at / updated_at：

- Vlan.device 可空（ConfigBase 上是必填）
- SnmpConfig.device 是一对一（ConfigBase 上是外键，基数由 1:1 变 1:N）；
  它自己的 created_at / updated_at 与 ConfigBase 同名同义，不重复添加
- Route 没有 device，归属通过 vrf 表达

Route 新增的 device 用 vrf.device 回填，因此先以 null=True 添加、回填后再收紧为 NOT NULL。
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def fill_route_device(apps, schema_editor):
    """Route 的 device 与 vrf.device 保持一致"""
    Route = apps.get_model("assets", "Route")
    for route in Route.objects.select_related("vrf").all():
        if route.device_id is None:
            route.device_id = route.vrf.device_id
            route.save(update_fields=["device"])


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0022_natrule_optional_m2m"),
    ]

    operations = [
        # --- Vlan：device 转必填，并补齐 ConfigBase 的其余字段 ---
        migrations.AlterField(
            model_name="vlan",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="assets.device", verbose_name="关联设备"
            ),
        ),
        migrations.AddField(
            model_name="vlan",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="是否生效"),
        ),
        migrations.AddField(
            model_name="vlan",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name="创建时间"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="vlan",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now, verbose_name="更新时间"),
            preserve_default=False,
        ),
        # --- SnmpConfig：一对一改外键（创建/更新时间已存在，只补 is_active） ---
        migrations.AlterField(
            model_name="snmpconfig",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="assets.device", verbose_name="关联设备"
            ),
        ),
        migrations.AddField(
            model_name="snmpconfig",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="是否生效"),
        ),
        # --- Route：新增 device（先可空以便回填）与本基类其余字段 ---
        migrations.AddField(
            model_name="route",
            name="device",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="assets.device",
                verbose_name="关联设备",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="是否生效"),
        ),
        migrations.AddField(
            model_name="route",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name="创建时间"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="route",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now, verbose_name="更新时间"),
            preserve_default=False,
        ),
        migrations.RunPython(fill_route_device, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="route",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="assets.device", verbose_name="关联设备"
            ),
        ),
    ]
