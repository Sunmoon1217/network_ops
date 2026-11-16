"""ArpMac 改继承 ConfigBase（在 assets 内完成，随后随家族 RENAME 迁 configs）。

原模型是裸 ``models.Model``，自带 device FK（related_name="arp_mac_entries"）与
created_at / updated_at。ConfigBase 同样提供这四个字段：

- ``device``：FK 目标与 on_delete 相同，只去掉全项目零消费点的 related_name，
  并统一 verbose_name 为基类的「关联设备」——只改迁移状态，不动列；
- ``created_at`` / ``updated_at``：同名同义，不重复添加；
- ``is_active``：新增，默认 True。

原有唯一约束 ``uni_arpmac_device_ip_mac`` 不含 app 名，保持不变。
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0036_remove_vlan_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="arpmac",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="assets.device",
                verbose_name="关联设备",
            ),
        ),
        migrations.AddField(
            model_name="arpmac",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="是否生效"),
        ),
    ]
