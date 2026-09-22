"""解析器 / 模板 / Saver 之间的契约测试。

三者的映射靠命名约定（模板的顶层 group 名 = config_json 的键 = Saver 的 keys）
加上 ``ingest.mapping`` 的归一层（别名键 / 别名字段 → 规范名），缺少校验时只会
**静默失效**：模板改了结构、或 Saver 注册到了错误的设备类型上，都不会报错，
只是数据不再入库。

本文件把这份约定固化下来，产出与消费的对账在**归一口径**（``canonical_key``）
下进行——``acl`` 与 ``policies`` 是同一语义。下面的缺口清单是**快照**：
修复缺口后需要同步更新常量，否则测试会失败并提醒。
"""

from ingest.mapping import canonical_key
from ingest.parsers.contract import KNOWN_MISSING_PRODUCER, KNOWN_UNCONSUMED_PRODUCTS
from ingest.parsers.factory import ParserFactory
from ingest.parsers.template_keys import template_keys
from ingest.savers.registry import all_savers


def _products_by_device_type() -> dict[str, set[str]]:
    """按设备类型聚合所有解析器声明的产出键（归一为规范键）"""
    products: dict[str, set[str]] = {}
    for (_vendor, device_type), parser_cls in ParserFactory._registry.items():
        products.setdefault(device_type, set()).update(canonical_key(k) for k in parser_cls.provides_keys)
    return products


def _consumers_by_device_type() -> dict[str, set[str]]:
    """按设备类型聚合所有 Saver 消费的键（归一为规范键）"""
    consumed: dict[str, set[str]] = {}
    for device_type, key in all_savers():
        consumed.setdefault(device_type, set()).add(canonical_key(key))
    return consumed


def test_provides_keys_match_template():
    """解析器声明的 provides_keys 必须与模板的顶层键完全一致"""
    mismatched = []
    for (vendor, device_type), parser_cls in sorted(ParserFactory._registry.items()):
        actual = template_keys(parser_cls.template_name)
        if actual != parser_cls.provides_keys:
            mismatched.append(f"{vendor}/{device_type} 声明={parser_cls.provides_keys} 模板={actual}")
    assert not mismatched, "以下解析器的 provides_keys 与模板不一致：\n" + "\n".join(mismatched)


def test_every_parser_template_exists():
    """每个已注册解析器的模板文件都必须存在"""
    missing = [
        f"{vendor}/{device_type} → {parser_cls.template_name}"
        for (vendor, device_type), parser_cls in ParserFactory._registry.items()
        if not template_keys(parser_cls.template_name)
    ]
    assert not missing, "以下解析器的模板缺失或没有任何顶层 group：\n" + "\n".join(missing)


def test_saver_keys_have_producer():
    """Saver 消费的键必须由该设备类型的某个解析器产出（归一口径，已知缺口除外）"""
    products = _products_by_device_type()
    unexpected = []
    for (device_type, key), saver_cls in sorted(all_savers().items()):
        if canonical_key(key) in products.get(device_type, set()):
            continue
        if (device_type, key) in KNOWN_MISSING_PRODUCER:
            continue
        unexpected.append(f"{saver_cls.__name__} 注册在 ({device_type}, {key!r})，但无任何解析器产出该键")
    assert not unexpected, "发现新的「消费无产出」缺口：\n" + "\n".join(unexpected)


def test_known_missing_producer_is_still_accurate():
    """已知缺口清单里不应残留已经修复的条目（归一口径下已有产出即算修复）"""
    products = _products_by_device_type()
    fixed = [
        f"({device_type}, {key!r}) 已有解析器产出，请从 KNOWN_MISSING_PRODUCER 移除"
        for (device_type, key) in KNOWN_MISSING_PRODUCER
        if canonical_key(key) in products.get(device_type, set())
    ]
    assert not fixed, "\n".join(fixed)


def test_unconsumed_products_match_snapshot():
    """「产出无消费」清单必须与快照一致（双向防回归）"""
    products = _products_by_device_type()
    consumed = _consumers_by_device_type()

    actual = {dt: sorted(keys - consumed.get(dt, set())) for dt, keys in products.items()}
    actual = {dt: keys for dt, keys in actual.items() if keys}
    expected = {dt: sorted(keys) for dt, keys in KNOWN_UNCONSUMED_PRODUCTS.items()}

    assert actual == expected, (
        "产出/消费缺口发生变化。\n"
        f"实际: {actual}\n"
        f"快照: {expected}\n"
        "若为修复缺口，请同步更新 KNOWN_UNCONSUMED_PRODUCTS。"
    )
