"""Service 唯一键从 (device, name) 放宽为自然键 (device, name, protocol, port, port2)。

拆行的前提：一个服务名允许承载多行端口定义（tcp 22 / udp 53 各一行）——原先按
(device, name) 唯一，Saver 只能把多行合并进一条 protocol/port，udp 语义丢失
（2026-09 修复，见 ServiceSaver）。

方向是**放宽**：原唯一蕴含新唯一，存量数据天然满足，零数据迁移、随时可回滚
（反向收紧前需先清理同名多行，否则 AddConstraint 会撞）。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0028_alter_route_destination_alter_subnet_network"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="service", name="uni_service_name"),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=["device", "name", "protocol", "port", "port2"],
                name="uni_service_natural_key",
            ),
        ),
    ]
