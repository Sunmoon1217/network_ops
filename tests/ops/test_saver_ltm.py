"""LTM 虚拟服务器及其 profiles / rules / persist 的 Saver 测试。

用 F5 解析器的**真实产出**驱动：这三个子表的数据嵌在 ``virtuals`` 里，
且 profiles / rules / persist 三种形态各不相同（list-of-dict / dict-with-list / dict）。
"""

import pytest

from assets.models import Device, LtmIRule, LtmPersist, LtmProfile, LtmVirtualServer
from ops.parsers.factory import ParserFactory
from ops.savers.lb import LBVirtualServerSaver

F5_VIRTUAL = """ltm virtual /Common/vs_web {
    destination /Common/10.0.0.1:443
    ip-protocol tcp
    pool /Common/pool_web
    profiles {
        /Common/http { }
        /Common/tcp { }
    }
    rules {
        /Common/irule_redirect
    }
    persist {
        /Common/cookie { }
    }
    source-address-translation {
        type automap
        pool /Common/snatpool
    }
}
"""


def _parsed() -> dict:
    return ParserFactory.get_parser_by_keys("F5", "slb").parse(F5_VIRTUAL)


@pytest.mark.django_db
def test_virtual_server_and_sub_tables_are_saved():
    device = Device.objects.create(hostname="_t_ltm_vs", device_type="slb")

    created, updated = LBVirtualServerSaver().save(device, _parsed())
    # 1 个 virtual + 2 个 profile + 1 个 irule + 1 个 persist
    assert (created, updated) == (5, 0)

    vs = LtmVirtualServer.objects.get(device=device)
    assert vs.name == "/Common/vs_web"
    assert vs.vs_address == "10.0.0.1"
    assert vs.vs_port == "443"
    assert vs.snat_pool == "/Common/snatpool"
    assert vs.persist == "/Common/cookie"
    assert vs.profiles == ["/Common/http", "/Common/tcp"]


@pytest.mark.django_db
def test_rules_are_flat_not_nested():
    """模板产出 rules 是 {'name': [...]}，拉平后不能出现嵌套 list"""
    device = Device.objects.create(hostname="_t_ltm_rules", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    vs = LtmVirtualServer.objects.get(device=device)
    assert vs.rules == ["/Common/irule_redirect"]
    assert LtmIRule.objects.get(device=device).name == "/Common/irule_redirect"


@pytest.mark.django_db
def test_profiles_type_from_basename_and_raw_keeps_source():
    """profile 的 type 取路径末段；raw 里留档来源 virtual server"""
    device = Device.objects.create(hostname="_t_ltm_prof", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    profiles = {profile.name: profile for profile in LtmProfile.objects.filter(device=device)}
    assert set(profiles) == {"/Common/http", "/Common/tcp"}
    assert profiles["/Common/http"].type == "http"
    assert profiles["/Common/tcp"].type == "tcp"
    assert profiles["/Common/http"].raw["virtual_server"] == "/Common/vs_web"


@pytest.mark.django_db
def test_persist_recorded_with_type():
    device = Device.objects.create(hostname="_t_ltm_persist", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    persist = LtmPersist.objects.get(device=device)
    assert persist.name == "/Common/cookie"
    assert persist.type == "cookie"


@pytest.mark.django_db
def test_sub_tables_are_idempotent():
    device = Device.objects.create(hostname="_t_ltm_idem", device_type="slb")
    saver = LBVirtualServerSaver()
    parsed = _parsed()

    assert saver.save(device, parsed)[0] == 5
    assert saver.save(device, parsed) == (0, 5)

    assert LtmVirtualServer.objects.filter(device=device).count() == 1
    assert LtmProfile.objects.filter(device=device).count() == 2
    assert LtmIRule.objects.filter(device=device).count() == 1
    assert LtmPersist.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_shared_profile_is_not_duplicated():
    """两个 virtual 用同一个 profile 时只应有一条记录，raw 记最后一次来源"""
    device = Device.objects.create(hostname="_t_ltm_share", device_type="slb")
    parsed = {
        "virtuals": [
            {
                "name": "/Common/vs1",
                "vs_address": "10.0.0.1",
                "vs_port": "80",
                "profiles": [{"name": "/Common/http"}],
            },
            {
                "name": "/Common/vs2",
                "vs_address": "10.0.0.2",
                "vs_port": "80",
                "profiles": [{"name": "/Common/http"}],
            },
        ]
    }

    LBVirtualServerSaver().save(device, parsed)

    assert LtmProfile.objects.filter(device=device).count() == 1
    assert LtmProfile.objects.get(device=device).raw["virtual_server"] == "/Common/vs2"


@pytest.mark.django_db
def test_virtual_without_sub_tables_still_saves():
    """没有 profiles / rules / persist 的 virtual 也不能报错"""
    device = Device.objects.create(hostname="_t_ltm_bare", device_type="slb")
    parsed = {"virtuals": {"name": "/Common/vs_bare", "vs_address": "10.0.0.9", "vs_port": "8080"}}

    assert LBVirtualServerSaver().save(device, parsed) == (1, 0)
    assert LtmVirtualServer.objects.get(device=device).profiles == []
