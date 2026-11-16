"""``Task.device`` 外键 → ``target_type`` / ``target_id`` / ``target_label`` 软引用（方案 C）。

**顺序是这次迁移的全部意义**：先加字段 → ``RunPython`` 回填存量 → 再删外键。
反过来的话，存量任务与设备的关联会全部丢光（见 ``handbook/design/task-framework.md`` §①）。

反向迁移同样安全：Django 逆序执行时会先重建 ``device`` 列，再跑本函数的 ``backwards``，
所以能按 ``target_*`` 写回 ``device_id``。
"""

from django.db import migrations, models


def backfill_device_target(apps, schema_editor):
    """存量 ``device_id`` → ``target_type="device"`` + ``target_id`` + ``target_label``。"""
    Task = apps.get_model("core", "Task")
    Device = apps.get_model("assets", "Device")

    legacy = Task.objects.exclude(device_id=None)
    hostnames = dict(Device.objects.filter(pk__in=legacy.values_list("device_id", flat=True)).values_list("pk", "hostname"))

    for task in legacy.iterator():
        task.target_type = "device"
        task.target_id = task.device_id
        task.target_label = hostnames.get(task.device_id, "")
        task.save(update_fields=["target_type", "target_id", "target_label"])

    expected = legacy.count()
    migrated = Task.objects.filter(target_type="device", target_id__isnull=False).count()
    if migrated != expected:
        raise RuntimeError(f"Task 作用目标回填不完整：存量关联设备 {expected} 行，回填后 {migrated} 行")


def backfill_device_fk(apps, schema_editor):
    """反向：软引用写回 ``device_id``（此时 ``device`` 列已被逆序重建）。"""
    Task = apps.get_model("core", "Task")

    for task in Task.objects.filter(target_type="device", target_id__isnull=False).iterator():
        task.device_id = task.target_id
        task.save(update_fields=["device_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_alter_stage_stage_type_alter_task_task_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="target_type",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="作用目标类型"),
        ),
        migrations.AddField(
            model_name="task",
            name="target_id",
            field=models.BigIntegerField(blank=True, null=True, verbose_name="作用目标ID"),
        ),
        migrations.AddField(
            model_name="task",
            name="target_label",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="作用目标名称"),
        ),
        migrations.RunPython(backfill_device_target, backfill_device_fk),
        migrations.RemoveField(
            model_name="task",
            name="device",
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(fields=["target_type", "target_id"], name="task_target_idx"),
        ),
    ]
