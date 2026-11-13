"""统一关系表（T3）的契约测试。

现阶段只做信息录入与查询：六类关系、唯一约束、自环拒绝、ci_id 存在性校验、
正反向过滤、最近一跳不展开，以及关系台账不被 ``purge_configs`` 误清。
"""

import pytest
from django.db import IntegrityError, transaction

from assets.models import CI_RELATION_CHOICES, CIRelationship, CIRelationType, CIType, ConfigBase, ConfigurationItem

CI_URL = "/api/assets/ci-relationships/"


def _ci(name: str) -> ConfigurationItem:
    return ConfigurationItem.objects.create(ci_type=CIType.PHYSICAL_SERVER, name=name)


def _rel(src: ConfigurationItem, dst: ConfigurationItem, rtype: str = CIRelationType.RUNS_ON) -> CIRelationship:
    return CIRelationship.objects.create(src_ci_id=src.ci_id, dst_ci_id=dst.ci_id, relation_type=rtype)


@pytest.mark.django_db
def test_six_relation_types_are_the_contract():
    values = {value for value, _label in CI_RELATION_CHOICES}
    assert len(values) == 6
    assert values == {
        CIRelationType.RUNS_ON,
        CIRelationType.DEPENDS_ON,
        CIRelationType.DEPLOYED_ON,
        CIRelationType.CONNECTED_TO,
        CIRelationType.LOCATED_IN,
        CIRelationType.MEMBER_OF,
    }


@pytest.mark.django_db
def test_duplicate_relation_rejected():
    """同一 (src, dst, type) 只允许一条；换类型可以并存"""
    a, b = _ci("a"), _ci("b")
    _rel(a, b)
    _rel(a, b, CIRelationType.DEPENDS_ON)
    with pytest.raises(IntegrityError), transaction.atomic():
        _rel(a, b)


@pytest.mark.django_db
def test_self_loop_rejected_by_db_and_api(operator_client):
    a = _ci("a")
    with pytest.raises(IntegrityError), transaction.atomic():
        _rel(a, a, CIRelationType.DEPENDS_ON)
    res = operator_client.post(
        CI_URL,
        {"src_ci_id": a.ci_id, "dst_ci_id": a.ci_id, "relation_type": CIRelationType.DEPENDS_ON},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_rejects_unknown_ci_id(operator_client):
    """弱关联不等于允许脏数据：录入时校验两端 ci_id 都存在"""
    a = _ci("a")
    res = operator_client.post(
        CI_URL,
        {"src_ci_id": a.ci_id, "dst_ci_id": "CI-does-not-exist", "relation_type": CIRelationType.RUNS_ON},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_create_returns_relation_type_display(operator_client):
    a, b = _ci("a"), _ci("b")
    res = operator_client.post(
        CI_URL,
        {"src_ci_id": a.ci_id, "dst_ci_id": b.ci_id, "relation_type": CIRelationType.RUNS_ON},
        format="json",
    )
    assert res.status_code == 201, res.content
    assert res.json()["relation_type_display"] == "运行于"


@pytest.mark.django_db
def test_api_filter_by_ci_id_direction_and_type(api_client):
    a, b, c = _ci("a"), _ci("b"), _ci("c")
    _rel(a, b, CIRelationType.RUNS_ON)
    _rel(b, c, CIRelationType.LOCATED_IN)
    _rel(a, c, CIRelationType.DEPENDS_ON)

    assert api_client.get(CI_URL).json()["count"] == 3
    # ci_id 命中任一端：b 有一条入边、一条出边
    assert len(api_client.get(CI_URL, {"ci_id": b.ci_id}).json()["results"]) == 2
    assert len(api_client.get(CI_URL, {"src_ci_id": a.ci_id}).json()["results"]) == 2
    assert len(api_client.get(CI_URL, {"dst_ci_id": c.ci_id}).json()["results"]) == 2
    assert api_client.get(CI_URL, {"relation_type": CIRelationType.RUNS_ON}).json()["count"] == 1


@pytest.mark.django_db
def test_only_direct_edges_are_stored():
    """上级归属只存最近一跳：不物化传递闭包，多跳遍历留给 T7"""
    a, b, c = _ci("a"), _ci("b"), _ci("c")
    _rel(a, b, CIRelationType.RUNS_ON)
    _rel(b, c, CIRelationType.LOCATED_IN)
    assert CIRelationship.objects.count() == 2
    assert not CIRelationship.objects.filter(src_ci_id=a.ci_id, dst_ci_id=c.ci_id).exists()


@pytest.mark.django_db
def test_relationship_is_not_configbase_subclass():
    """purge_configs 按 ConfigBase.__subclasses__() 枚举；关系台账不能被配置清理带走"""
    assert CIRelationship not in ConfigBase.__subclasses__()


@pytest.mark.django_db
def test_api_search_and_pagination(api_client):
    a = _ci("a")
    for index in range(4):
        _rel(a, _ci(f"b{index}"))
    page = api_client.get(CI_URL, {"page_size": 2}).json()
    assert page["count"] == 4
    assert len(page["results"]) == 2
    assert api_client.get(CI_URL, {"search": a.ci_id}).json()["count"] == 4
