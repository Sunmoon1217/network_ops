import json
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from ingest.parsers.factory import ParserFactory

_TMPLS_DIR = Path(__file__).resolve().parent.parent / "parsers" / "tmpls"


def _find_template(name: str) -> Path | None:
    """在 configs 和 running 子目录中查找模板"""
    for subdir in ("configs", "running"):
        path = _TMPLS_DIR / subdir / name
        if path.exists():
            return path
    return None


@require_GET
def parser_list(request):
    """获取所有已注册的解析器列表"""
    parsers = []
    for (vendor, device_type), parser_cls in ParserFactory._registry.items():
        parsers.append(
            {
                "vendor": vendor,
                "device_type": device_type,
                "class_name": parser_cls.__name__,
                "template_name": parser_cls.template_name,
                "description": parser_cls.__doc__ or "",
            }
        )
    return JsonResponse({"parsers": parsers})


@require_GET
def parser_mapping(request):
    """映射清单：解析器 → 模板 → 产出键 →（归一）→ Saver → 模型，并暴露契约缺口

    用于回答"这台设备会解析出什么、进哪些表"，以及发现
    「模板改了结构导致 Saver 静默失效」这类问题。

    产出与消费的对账在**归一口径**（``ingest.mapping.canonical_key``）下进行；
    ``consumers`` 条目附 ``canonical_key`` 与 ``models``（Saver 写入的模型），
    顶层另给 ``key_aliases`` / ``field_aliases`` 两张归一声明表与按 Saver
    聚合的 ``savers`` 清单——即解析器 / 关键字内部结构差异 / Saver / 模型
    的完整关联关系。
    """
    from ingest.mapping import FIELD_ALIASES, KEY_ALIASES, canonical_key
    from ingest.parsers.contract import KNOWN_MISSING_PRODUCER
    from ingest.parsers.template_keys import template_has_dynamic_groups, template_keys
    from ingest.savers.registry import all_savers

    savers = all_savers()

    # 按设备类型聚合 Saver：{device_type: {key: saver 类名}}
    consumers_by_type: dict[str, dict[str, str]] = {}
    for (device_type, key), saver_cls in savers.items():
        consumers_by_type.setdefault(device_type, {})[key] = saver_cls.__name__

    parsers_payload = []
    produced_by_type: dict[str, set[str]] = {}
    for (vendor, device_type), parser_cls in sorted(ParserFactory._registry.items()):
        template_keys_actual = template_keys(parser_cls.template_name)
        declared_keys = list(parser_cls.provides_keys)
        produced_by_type.setdefault(device_type, set()).update(canonical_key(k) for k in declared_keys)

        consumers = consumers_by_type.get(device_type, {})
        parsers_payload.append(
            {
                "vendor": vendor,
                "device_type": device_type,
                "class_name": parser_cls.__name__,
                "template_name": parser_cls.template_name,
                "template_exists": _find_template(parser_cls.template_name) is not None,
                "provides_keys": declared_keys,
                "template_keys": template_keys_actual,
                "keys_match": template_keys_actual == declared_keys,
                "has_dynamic_group_names": template_has_dynamic_groups(parser_cls.template_name),
                "consumers": [
                    {
                        "key": k,
                        "saver": consumers[k],
                        "canonical_key": canonical_key(k),
                        # 模型短名（如 "Policy"），完整点路径见顶层 savers 清单
                        "models": [p.rsplit(".", 1)[-1] for p in savers[(device_type, k)].model_paths],
                    }
                    for k in declared_keys
                    if k in consumers
                ],
                "unconsumed_keys": [k for k in declared_keys if k not in consumers],
            }
        )

    missing_producers = [
        {
            "device_type": device_type,
            "key": key,
            "saver": saver_cls.__name__,
            "note": KNOWN_MISSING_PRODUCER.get((device_type, key), ""),
        }
        for (device_type, key), saver_cls in sorted(savers.items())
        if canonical_key(key) not in produced_by_type.get(device_type, set())
    ]

    # 按 Saver 类聚合的「Saver → 模型」清单（同一 Saver 的多个键 / 多个类型只列一次）
    savers_payload: list[dict] = []
    by_class: dict[str, dict] = {}
    for (device_type, key), saver_cls in sorted(savers.items()):
        entry = by_class.setdefault(
            saver_cls.__name__,
            {
                "saver": saver_cls.__name__,
                "device_types": [],
                "keys": [],
                "canonical_keys": [],
                "model_paths": list(saver_cls.model_paths),
                "models": [p.rsplit(".", 1)[-1] for p in saver_cls.model_paths],
            },
        )
        if device_type not in entry["device_types"]:
            entry["device_types"].append(device_type)
        if key not in entry["keys"]:
            entry["keys"].append(key)
        ck = canonical_key(key)
        if ck not in entry["canonical_keys"]:
            entry["canonical_keys"].append(ck)
    savers_payload = list(by_class.values())

    summary = {
        "parser_count": len(parsers_payload),
        "saver_count": len({cls.__name__ for cls in savers.values()}),
        "keys_mismatch": sum(1 for p in parsers_payload if not p["keys_match"]),
        "missing_producer_count": len(missing_producers),
        "unconsumed_count": sum(len(p["unconsumed_keys"]) for p in parsers_payload),
    }
    return JsonResponse(
        {
            "summary": summary,
            "parsers": parsers_payload,
            "missing_producers": missing_producers,
            "key_aliases": KEY_ALIASES,
            "field_aliases": FIELD_ALIASES,
            "savers": savers_payload,
        }
    )


@require_GET
def parser_template_list(request):
    """获取所有模板文件列表"""
    templates = []
    for subdir in ("configs", "running"):
        for f in (_TMPLS_DIR / subdir).glob("*.ttp"):
            templates.append({"name": f.name, "group": subdir, "size": f.stat().st_size})
    return JsonResponse({"templates": templates})


@require_GET
def parser_template_detail(request, name):
    """获取模板文件内容"""
    path = _find_template(name)
    if not path:
        return JsonResponse({"error": f"模板不存在: {name}"}, status=404)
    return JsonResponse(
        {
            "name": name,
            "content": path.read_text(encoding="utf-8"),
            "size": path.stat().st_size,
        }
    )


@require_http_methods(["PUT"])
def parser_template_update(request, name):
    """更新模板文件内容"""
    path = _find_template(name)
    if not path:
        return JsonResponse({"error": f"模板不存在: {name}"}, status=404)
    try:
        data = json.loads(request.body)
        content = data.get("content", "")
        path.write_text(content, encoding="utf-8")
        return JsonResponse({"name": name, "size": path.stat().st_size, "message": "保存成功"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
