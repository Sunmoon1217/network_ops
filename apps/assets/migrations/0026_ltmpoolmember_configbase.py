"""LtmPoolMember 改为继承 ConfigBase。

原来它是裸 ``models.Model``，只有一个 ``pool_name`` 字符串，没有 ``device``：
不同设备上的同名池成员在库里无法区分，资产分析、路径追踪按 ``pool_name``
全局匹配时会把它们串到一起，``LBPoolSaver`` 先删后建时也会跨设备误删。

改为继承 ConfigBase 后补上 ``device``（非空外键）与
``is_active`` / ``created_at`` / ``updated_at``，并新增
``(device, pool_name, name, port)`` 唯一约束 —— 唯一性必须带 ``port``：
F5 同一节点可以在两个端口上做成员，剥掉 ``/Common/node_a:80`` 的端口后
``name`` 都是 ``node_a``，只约束 ``name`` 会误杀合法数据。

存量数据只有 ``pool_name``，而 ``pool_name`` 无法唯一映射到设备（同名池可能
存在于多台设备上），因此：

- 能唯一命中某台设备的池 → 回填 ``device``
- 命中 0 个（孤儿）或命中多台设备（有歧义）→ **删除**，并在迁移输出里逐条打印
- 回填后再按 ``(device, pool_name, name, port)`` 去重，保留 pk 最小的一条

``device`` 先以 ``null=True`` 添加，回填/清理完成后再收紧为 NOT NULL。
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def fill_member_device(apps, schema_editor):
    """用池名反查设备回填 LtmPoolMember.device，无法唯一确定的行直接删除"""
    LtmPoolMember = apps.get_model("assets", "LtmPoolMember")
    LtmPool = apps.get_model("assets", "LtmPool")

    # pool_name -> 拥有同名池的设备集合；LtmPool 的 (device, name) 唯一，
    # 所以集合里的元素一定互不相同
    devices_by_pool_name: dict[str, set[int]] = {}
    for name, device_id in LtmPool.objects.values_list("name", "device_id"):
        devices_by_pool_name.setdefault(name, set()).add(device_id)

    unresolved: list[tuple[int, str, str, int]] = []
    for member in LtmPoolMember.objects.all():
        candidates = devices_by_pool_name.get(member.pool_name, set())
        if len(candidates) == 1:
            member.device_id = next(iter(candidates))
            member.save(update_fields=["device"])
        else:
            unresolved.append((member.pk, member.pool_name, member.name, len(candidates)))

    if unresolved:
        print(f"\n  LtmPoolMember: {len(unresolved)} 条无法确定归属，已删除（pk, pool_name, name, 候选设备数）：")
        for row in unresolved:
            print(f"    pk={row[0]} pool_name={row[1]!r} name={row[2]!r} 候选设备数={row[3]}")
        LtmPoolMember.objects.filter(pk__in=[row[0] for row in unresolved]).delete()


def dedupe_members(apps, schema_editor):
    """按新唯一约束的字段组合去重，保留 pk 最小的一条"""
    LtmPoolMember = apps.get_model("assets", "LtmPoolMember")

    seen: set[tuple] = set()
    duplicate_pks: list[int] = []
    rows = LtmPoolMember.objects.order_by("pk").values_list("pk", "device_id", "pool_name", "name", "port")
    for pk, device_id, pool_name, name, port in rows:
        key = (device_id, pool_name, name, port)
        if key in seen:
            duplicate_pks.append(pk)
        else:
            seen.add(key)

    if duplicate_pks:
        print(f"\n  LtmPoolMember: 去重删除 {len(duplicate_pks)} 条重复成员（保留每组 pk 最小的一条）")
        LtmPoolMember.objects.filter(pk__in=duplicate_pks).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0025_service_unique_per_device"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="ltmpoolmember",
            options={
                "ordering": ("device", "pool_name", "name", "-pk"),
                "verbose_name": "LTM Pool Member",
                "verbose_name_plural": "LTM Pool Member",
            },
        ),
        migrations.AddField(
            model_name="ltmpoolmember",
            name="device",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="assets.device",
                verbose_name="关联设备",
            ),
        ),
        migrations.AddField(
            model_name="ltmpoolmember",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="是否生效"),
        ),
        migrations.AddField(
            model_name="ltmpoolmember",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name="创建时间"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ltmpoolmember",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now, verbose_name="更新时间"),
            preserve_default=False,
        ),
        migrations.RunPython(fill_member_device, migrations.RunPython.noop),
        migrations.RunPython(dedupe_members, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ltmpoolmember",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="assets.device", verbose_name="关联设备"
            ),
        ),
        migrations.AddConstraint(
            model_name="ltmpoolmember",
            constraint=models.UniqueConstraint(
                fields=("device", "pool_name", "name", "port"), name="uni_pool_member_device_pool_node_port"
            ),
        ),
    ]
