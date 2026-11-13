"""Service 唯一键从 (device, name) 放宽为自然键 (device, name, protocol, port, port2)。

拆行的前提：一个服务名允许承载多行端口定义（tcp 22 / udp 53 各一行）——原先按
(device, name) 唯一，Saver 只能把多行合并进一条 protocol/port，udp 语义丢失
（2026-09 修复，见 ServiceSaver）。

方向是**放宽**：原唯一蕴含新唯一，存量数据天然满足，零数据迁移、随时可回滚
（反向收紧前需先清理同名多行，否则 AddConstraint 会撞）。

⚠️ 跨库改造（2026-11）：五列唯一键在 utf8mb4 下是 3108 字节（3 个 varchar(255) 各
1020 + 两列短字段），超过 InnoDB 3072 字节的索引上限，MySQL 上 ``ADD CONSTRAINT``
直接报 1071。所以唯一键改为按后端分别建（state 侧仍是普通 UniqueConstraint）：

* PostgreSQL：普通复合唯一约束，与改造前完全一致；
* MySQL 8.0.13+：函数唯一索引 ``(device_id, MD5(CONCAT_WS('|', name, protocol, port, port2)))``。
  语义等价（排除 MD5 碰撞），不截断字段、大小写敏感性与 PG 一致（哈希按字节比较）。
  若要做到 8.0.11 也能装，只能降到前缀索引——那会把「前 N 个字符相同」当重复，语义不等价。
"""

from django.db import migrations, models

_NATURAL_KEY_COLUMNS = "device_id, name, protocol, port, port2"
_MYSQL_HASH_EXPR = "(device_id, (MD5(CONCAT_WS('|', name, protocol, port, port2))))"


def create_natural_key(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute(f"CREATE UNIQUE INDEX uni_service_natural_key ON assets_service {_MYSQL_HASH_EXPR}")
    else:
        schema_editor.execute(f"ALTER TABLE assets_service ADD CONSTRAINT uni_service_natural_key UNIQUE ({_NATURAL_KEY_COLUMNS})")


def drop_natural_key(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute("DROP INDEX uni_service_natural_key ON assets_service")
    else:
        schema_editor.execute("ALTER TABLE assets_service DROP CONSTRAINT uni_service_natural_key")


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0028_alter_route_destination_alter_subnet_network"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="service", name="uni_service_name"),
        # state 侧照旧声明唯一约束（模型 Meta 与迁移状态一致）；实际建索引走下面的
        # RunPython，因为 MySQL 要换成函数索引。
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="service",
                    constraint=models.UniqueConstraint(
                        fields=["device", "name", "protocol", "port", "port2"],
                        name="uni_service_natural_key",
                    ),
                ),
            ],
            database_operations=[],
        ),
        # atomic=False：MySQL 不能回滚 DDL，Django 禁止在事务里执行建索引语句
        # （TransactionManagementError）。本迁移只动 schema，不裹事务是安全的。
        migrations.RunPython(create_natural_key, drop_natural_key, atomic=False),
    ]
