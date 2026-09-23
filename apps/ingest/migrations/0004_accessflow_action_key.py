"""AccessFlow 唯一键加入 action（九元组 → 十元组）。

业务含义：同一条五元组访问流被 allow 与 deny 策略命中时是**两条独立的流**——
「遗漏」审计拿 allow 行对照应放、「多开」审计拿 deny 行对照应拒，混在一行里
两种审计互斥。contexts 里各 context 本就带 action（``_context_of``），存量数据
存在**同一行混着 allow/deny context** 的情况，必须先拆行再上约束。

operations 顺序是硬约束，别调：

1. ``AddField(action, default="allow")``——先给全部存量行一个占位值；
2. ``RemoveConstraint(uni_accessflow_key)``——**必须在拆行之前**解开九元组唯一，
   否则「同一九元组克隆出第二行」直接撞旧约束；
3. ``RunPython(split)``——按 context 的 action 拆混合行 / 校准单组行的 action；
4. ``AlterField``——去掉 default，终态与模型字段一致（否则 makemigrations 持续报差）；
5. ``AddConstraint(uni_accessflow_action_key)``——此时数据已保证十元组唯一。

反向（reverse）按逆序执行：先摘十元组约束 → 合并同九元组行 → 带回 default →
上回九元组约束 → 删 action 字段——合并放在 AddConstraint(九元组) 之前，
反向同样撞不了唯一约束。
"""

from django.db import migrations, models

#: 迁移冻结时的 action 取值（与 assets.Policy 归一词一致）
ALLOW = "allow"
DENY = "deny"
VALID = {ALLOW, DENY}


def _group_by_action(contexts: dict) -> dict[str, dict]:
    """contexts → {action: 该动作的子 contexts}；action 缺失/非法按 allow 兜底。"""
    groups: dict[str, dict] = {}
    for key, ctx in (contexts or {}).items():
        raw = str((ctx or {}).get("action") or ALLOW).strip().lower()
        groups.setdefault(raw if raw in VALID else ALLOW, {})[key] = ctx
    return groups


def _device_ids(contexts: dict) -> list[int]:
    # 从键拆而不是读 ctx["device_id"]：键格式 "<device_id>:<policy_pk>" 是写死的
    # 契约（见 AccessFlow docstring），比逐条读 ctx 字段对历史数据更稳。
    return sorted({int(k.split(":", 1)[0]) for k in contexts})


def _policy_ids(contexts: dict) -> list[int]:
    return sorted({int(k.split(":", 1)[1]) for k in contexts})


def split_mixed_rows(apps, schema_editor) -> None:
    """按 context 的 action 拆开混合行，并把单组行的 action 校准为真实值。"""
    AccessFlow = apps.get_model("operator", "AccessFlow")
    clones = []
    for row in AccessFlow.objects.all().iterator():
        groups = _group_by_action(row.contexts)
        if not groups:
            # contexts 为空的行不应存在；保持 AddField 给的占位 allow 不动
            continue
        # 留哪组在原行：有 allow 优先（主语义行），否则字典序首个；其余克隆新行
        primary = ALLOW if ALLOW in groups else sorted(groups)[0]
        kept = groups[primary]
        if row.action != primary or len(groups) > 1:
            row.action = primary
            row.contexts = kept
            row.device_ids = _device_ids(kept)
            row.policy_ids = _policy_ids(kept)
            row.save(update_fields=["action", "contexts", "device_ids", "policy_ids"])
        for action, ctxs in groups.items():
            if action == primary:
                continue
            clones.append(
                AccessFlow(
                    src_ip=row.src_ip,
                    src_prefix=row.src_prefix,
                    src_range_end=row.src_range_end,
                    dst_ip=row.dst_ip,
                    dst_prefix=row.dst_prefix,
                    dst_range_end=row.dst_range_end,
                    protocol=row.protocol,
                    port=row.port,
                    port2=row.port2,
                    action=action,
                    contexts=ctxs,
                    device_ids=_device_ids(ctxs),
                    policy_ids=_policy_ids(ctxs),
                )
            )
    if clones:
        AccessFlow.objects.bulk_create(clones, batch_size=500)


def merge_rows_for_reverse(apps, schema_editor) -> None:
    """反向：同一九元组的多行合并回一行（contexts 合并、保留最小 pk）。"""
    AccessFlow = apps.get_model("operator", "AccessFlow")
    buckets: dict[tuple, list] = {}
    for row in AccessFlow.objects.all().iterator():
        key9 = (
            row.src_ip,
            row.src_prefix,
            row.src_range_end,
            row.dst_ip,
            row.dst_prefix,
            row.dst_range_end,
            row.protocol,
            row.port,
            row.port2,
        )
        buckets.setdefault(key9, []).append(row)
    for rows in buckets.values():
        if len(rows) == 1:
            continue
        rows.sort(key=lambda r: r.pk)
        keep, others = rows[0], rows[1:]
        merged: dict = {}
        for row in rows:
            merged.update(row.contexts or {})
        keep.contexts = merged
        keep.device_ids = _device_ids(merged)
        keep.policy_ids = _policy_ids(merged)
        keep.save(update_fields=["contexts", "device_ids", "policy_ids"])
        AccessFlow.objects.filter(pk__in=[r.pk for r in others]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operator", "0003_remove_internet_analysis_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="accessflow",
            name="action",
            field=models.CharField(choices=[("allow", "放行"), ("deny", "拒绝")], default="allow", max_length=10, verbose_name="动作"),
        ),
        migrations.RemoveConstraint(model_name="accessflow", name="uni_accessflow_key"),
        migrations.RunPython(split_mixed_rows, merge_rows_for_reverse),
        migrations.AlterField(
            model_name="accessflow",
            name="action",
            field=models.CharField(choices=[("allow", "放行"), ("deny", "拒绝")], max_length=10, verbose_name="动作"),
        ),
        migrations.AddConstraint(
            model_name="accessflow",
            constraint=models.UniqueConstraint(
                fields=[
                    "src_ip",
                    "src_prefix",
                    "src_range_end",
                    "dst_ip",
                    "dst_prefix",
                    "dst_range_end",
                    "protocol",
                    "port",
                    "port2",
                    "action",
                ],
                name="uni_accessflow_action_key",
            ),
        ),
    ]
