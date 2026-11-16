"""assets → configs 批量拆分（state 侧）：只删 state，不删表。

25 个模型从 assets 的迁移状态移除，DB 层完全不动（SeparateDatabaseAndState 的
database_operations 为空）；物理表改名由 configs/0002 的 RunSQL 负责。
字段/约束终态逐字段照抄 assets 迁移链到 0037 为止的 ProjectState，见 configs/0002。
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0037_arpmac_configbase"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="DeviceConfig",
                ),
                migrations.DeleteModel(
                    name="ArpMac",
                ),
                migrations.DeleteModel(
                    name="Route",
                ),
                migrations.DeleteModel(
                    name="NatRule",
                ),
                migrations.DeleteModel(
                    name="Policy",
                ),
                migrations.DeleteModel(
                    name="Service",
                ),
                migrations.DeleteModel(
                    name="AddressBook",
                ),
                migrations.DeleteModel(
                    name="GtmPool",
                ),
                migrations.DeleteModel(
                    name="GtmWideip",
                ),
                migrations.DeleteModel(
                    name="GtmVServer",
                ),
                migrations.DeleteModel(
                    name="GtmServer",
                ),
                migrations.DeleteModel(
                    name="GtmDatacenter",
                ),
                migrations.DeleteModel(
                    name="LtmPersist",
                ),
                migrations.DeleteModel(
                    name="LtmSNAT",
                ),
                migrations.DeleteModel(
                    name="LtmIRule",
                ),
                migrations.DeleteModel(
                    name="LtmProfile",
                ),
                migrations.DeleteModel(
                    name="LtmPoolMember",
                ),
                migrations.DeleteModel(
                    name="LtmPool",
                ),
                migrations.DeleteModel(
                    name="LtmVirtualServer",
                ),
                migrations.DeleteModel(
                    name="SyslogConfig",
                ),
                migrations.DeleteModel(
                    name="NtpConfig",
                ),
                migrations.DeleteModel(
                    name="SnmpConfig",
                ),
                migrations.DeleteModel(
                    name="DeviceAccount",
                ),
                migrations.DeleteModel(
                    name="Interface",
                ),
                migrations.DeleteModel(
                    name="Vrf",
                ),
            ],
        ),
    ]
