"""软资产扩展表（T4）的契约测试。

两张表只承载归并产出的专属字段，公共属性在主表；这里锁住类型约束、归一键唯一、
与 CI 一对一、级联删除，以及不被 ``purge_configs`` 枚举。
"""

import pytest
from django.db import IntegrityError, transaction

from assets.models import CIType, ConfigBase, ConfigurationItem, DomainAsset, LoadBalancerService


def _ci(ci_type: str, name: str) -> ConfigurationItem:
    return ConfigurationItem.objects.create(ci_type=ci_type, name=name)


@pytest.mark.django_db
def test_domain_asset_key_is_unique():
    """一个 FQDN 只能有一条资产：归并去重的落点"""
    DomainAsset.objects.create(ci=_ci(CIType.DOMAIN, "a.example.com"), fqdn="a.example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        DomainAsset.objects.create(ci=_ci(CIType.DOMAIN, "a.example.com"), fqdn="a.example.com")


@pytest.mark.django_db
def test_load_balancer_asset_key_is_unique():
    """一个 VIP#port 只能有一条资产"""
    LoadBalancerService.objects.create(ci=_ci(CIType.LOAD_BALANCER_SERVICE, "10.1.1.10#443"), asset_key="10.1.1.10#443", vip="10.1.1.10", port="443")
    with pytest.raises(IntegrityError), transaction.atomic():
        LoadBalancerService.objects.create(ci=_ci(CIType.LOAD_BALANCER_SERVICE, "10.1.1.10#443"), asset_key="10.1.1.10#443", vip="10.1.1.10", port="443")


@pytest.mark.django_db
def test_soft_assets_require_matching_ci_type():
    """域名表只能挂 DOMAIN，LB 表只能挂 LOAD_BALANCER_SERVICE"""
    with pytest.raises(ValueError, match="ci_type"):
        DomainAsset.objects.create(ci=_ci(CIType.LOAD_BALANCER_SERVICE, "10.1.1.10#443"), fqdn="a.example.com")
    with pytest.raises(ValueError, match="ci_type"):
        LoadBalancerService.objects.create(ci=_ci(CIType.DOMAIN, "a.example.com"), asset_key="10.1.1.10#443", vip="10.1.1.10")


@pytest.mark.django_db
def test_soft_assets_are_not_configbase_subclass():
    """归并结果是资产台账，不是配置解析产物：purge_configs 不能清它"""
    assert DomainAsset not in ConfigBase.__subclasses__()
    assert LoadBalancerService not in ConfigBase.__subclasses__()


@pytest.mark.django_db
def test_deleting_ci_cascades_to_extension():
    ci = _ci(CIType.DOMAIN, "a.example.com")
    DomainAsset.objects.create(ci=ci, fqdn="a.example.com")
    ci.delete()
    assert not DomainAsset.objects.exists()
