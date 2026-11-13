"""统一配置项体系（T1）的契约测试。

现阶段只做信息录入与查询：ci_id 稳定锚点、类型匹配、扩展一对一、
API 分页 / 搜索 / 过滤，以及 CI 台账不被 ``purge_configs`` 误清。
"""

import pytest
from django.db import IntegrityError, transaction

from assets.models import CIType, ConfigBase, ConfigurationItem, PhysicalServer

CI_URL = "/api/assets/configuration-items/"
PHY_URL = "/api/assets/physical-servers/"


def _ci(ci_type: str, name: str) -> ConfigurationItem:
    return ConfigurationItem.objects.create(ci_type=ci_type, name=name)


@pytest.mark.django_db
def test_ci_id_generated_on_create_and_stable():
    """ci_id 是 T15 纳管锚点：改名 / 二次 save 都不能让它变"""
    ci = _ci(CIType.PHYSICAL_SERVER, "host-01")

    assert ci.ci_id.startswith("CI-")
    assert len(ci.ci_id) == len("CI-") + 12
    original = ci.ci_id
    ci.name = "host-renamed"
    ci.save()
    ci.refresh_from_db()
    assert ci.ci_id == original


@pytest.mark.django_db
def test_ci_id_is_unique():
    other = _ci(CIType.VIRTUAL_MACHINE, "vm-01")
    with pytest.raises(IntegrityError), transaction.atomic():
        ConfigurationItem.objects.create(ci_id=other.ci_id, ci_type=CIType.VIRTUAL_MACHINE, name="vm-02")


@pytest.mark.django_db
def test_ci_is_not_configbase_subclass():
    """purge_configs 按 ConfigBase.__subclasses__() 枚举；CI 台账不能被配置清理带走"""
    assert ConfigurationItem not in ConfigBase.__subclasses__()
    assert PhysicalServer not in ConfigBase.__subclasses__()


@pytest.mark.django_db
def test_extension_requires_matching_ci_type():
    ci = _ci(CIType.VIRTUAL_MACHINE, "vm-01")
    with pytest.raises(ValueError, match="ci_type"):
        PhysicalServer.objects.create(ci=ci, hostname="wrong")


@pytest.mark.django_db
def test_extension_is_one_to_one_with_ci():
    ci = _ci(CIType.PHYSICAL_SERVER, "host-01")
    PhysicalServer.objects.create(ci=ci, hostname="host-01")
    with pytest.raises(IntegrityError), transaction.atomic():
        PhysicalServer.objects.create(ci=ci, hostname="dup")


@pytest.mark.django_db
def test_api_list_search_filter_and_pagination(api_client):
    for index in range(3):
        _ci(CIType.PHYSICAL_SERVER, f"host-{index}")
    _ci(CIType.VIRTUAL_MACHINE, "vm-alpha")

    payload = api_client.get(CI_URL).json()
    assert payload["count"] == 4
    assert all(row["ci_id"].startswith("CI-") for row in payload["results"])

    by_type = api_client.get(CI_URL, {"ci_type": CIType.PHYSICAL_SERVER}).json()
    assert by_type["count"] == 3

    by_search = api_client.get(CI_URL, {"search": "vm-alpha"}).json()
    assert by_search["count"] == 1
    assert by_search["results"][0]["name"] == "vm-alpha"

    page = api_client.get(CI_URL, {"page_size": 2}).json()
    assert page["count"] == 4
    assert len(page["results"]) == 2


@pytest.mark.django_db
def test_api_create_ignores_ci_id_and_monitor_status(operator_client):
    """ci_id 服务端生成、monitor_status 是 T15 预留字段，都不接受客户端指定"""
    res = operator_client.post(
        CI_URL,
        {
            "ci_id": "CI-FORGED",
            "ci_type": CIType.APPLICATION_SERVICE,
            "name": "svc-01",
            "monitor_status": "down",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    ci = ConfigurationItem.objects.get(name="svc-01")
    assert ci.ci_id.startswith("CI-") and ci.ci_id != "CI-FORGED"
    assert ci.monitor_status == ""


@pytest.mark.django_db
def test_api_create_extension(operator_client):
    ci = _ci(CIType.PHYSICAL_SERVER, "host-01")
    res = operator_client.post(PHY_URL, {"ci": ci.pk, "hostname": "host-01", "cpu_cores": 32}, format="json")
    assert res.status_code == 201, res.content
    assert PhysicalServer.objects.get(ci=ci).cpu_cores == 32


@pytest.mark.django_db
def test_api_rejects_mismatched_ci_type(operator_client):
    """扩展模型不能挂到别的类型上：序列化器层挡住，返回 400 而不是 500"""
    ci = _ci(CIType.VIRTUAL_MACHINE, "vm-01")
    res = operator_client.post(PHY_URL, {"ci": ci.pk, "hostname": "wrong"}, format="json")
    assert res.status_code == 400
