"""A10 SLB Saver 测试。

用 A10 解析器的真实产出驱动，覆盖 service-group → LtmPool/LtmPoolMember 与
virtual-server → LtmVirtualServer/LtmProfile/LtmPersist 两段映射。字段对应关系
（A10 vs F5）见 ``savers/a10_lb.py`` 的模块 docstring。
"""

import pytest

from assets.models import Device, LtmPersist, LtmPool, LtmPoolMember, LtmProfile, LtmVirtualServer
from ingest.parsers.factory import ParserFactory
from ingest.savers.a10_lb import A10ServiceGroupSaver, A10VirtualServerSaver

A10_CONFIG = """slb server server1 10.1.1.1
   port 80 tcp
slb service-group sg1 tcp
    method round-robin
    health-check hc1
    member 10.1.1.1:80
    member 10.1.1.2:8080
slb virtual-server vs1 10.2.2.2
   port 80 tcp
      service-group sg1
      source-nat pool snatpool1
      template http http-tmpl
      template persist cookie cookie-persist
      template client-ssl ssl-tmpl
"""


def _parsed(cfg: str = A10_CONFIG) -> dict:
    return ParserFactory.get_parser_by_keys("A10", "slb").parse(cfg)


@pytest.mark.django_db
def test_service_group_and_members_are_saved():
    device = Device.objects.create(hostname="_t_a10_sg", device_type="slb")

    # 只计 LtmPool 的 created（成员走 bulk_create，与 F5 LBPoolSaver 口径一致）
    assert A10ServiceGroupSaver().save(device, _parsed()) == (1, 0)

    pool = LtmPool.objects.get(device=device, name="sg1")
    assert pool.mode == "round-robin"
    assert pool.monitors == ["hc1"]

    members = {m.port: m for m in LtmPoolMember.objects.filter(device=device, pool_name="sg1")}
    assert set(members) == {"80", "8080"}
    # A10 成员没有独立 node 名，用地址充当成员名，地址列原样落地址
    assert members["80"].name == "10.1.1.1"
    assert members["80"].address == "10.1.1.1"
    assert members["8080"].address == "10.1.1.2"


@pytest.mark.django_db
def test_service_group_without_health_check_gets_empty_monitors():
    device = Device.objects.create(hostname="_t_a10_sg_nomon", device_type="slb")
    cfg = """slb service-group sg2 tcp
    method least-connection
"""
    A10ServiceGroupSaver().save(device, ParserFactory.get_parser_by_keys("A10", "slb").parse(cfg))

    pool = LtmPool.objects.get(device=device, name="sg2")
    assert pool.monitors == []
    assert pool.mode == "least-connection"


@pytest.mark.django_db
def test_virtual_server_and_sub_tables_are_saved():
    device = Device.objects.create(hostname="_t_a10_vs", device_type="slb")

    # 1 virtual + 2 profile + 1 persist
    assert A10VirtualServerSaver().save(device, _parsed()) == (4, 0)

    vs = LtmVirtualServer.objects.get(device=device)
    assert vs.name == "vs1:80"
    assert vs.vs_address == "10.2.2.2"
    assert vs.vs_port == "80"
    assert vs.protocol == "tcp"
    assert vs.status == "enabled"
    assert vs.pool == "sg1"
    assert vs.snat_type == "pool"
    assert vs.snat_pool == "snatpool1"
    assert vs.persist == "cookie-persist"
    assert vs.profiles == ["http-tmpl", "ssl-tmpl"]

    profiles = {p.name: p for p in LtmProfile.objects.filter(device=device)}
    assert set(profiles) == {"http-tmpl", "ssl-tmpl"}
    assert profiles["http-tmpl"].type == "http"
    assert profiles["ssl-tmpl"].type == "client-ssl"

    persist = LtmPersist.objects.get(device=device)
    assert persist.name == "cookie-persist"
    assert persist.type == "cookie"


@pytest.mark.django_db
def test_multiple_ports_yield_distinct_virtual_servers():
    """A10 一个 virtual-server 挂多个 port，name 用 {vs_name}:{port} 区分"""
    cfg = """slb virtual-server vs1 10.2.2.2
   port 80 tcp
      service-group sg1
   port 443 tcp
      service-group sg2
"""
    device = Device.objects.create(hostname="_t_a10_multi", device_type="slb")
    A10VirtualServerSaver().save(device, ParserFactory.get_parser_by_keys("A10", "slb").parse(cfg))

    names = set(LtmVirtualServer.objects.filter(device=device).values_list("name", flat=True))
    assert names == {"vs1:80", "vs1:443"}


@pytest.mark.django_db
def test_virtual_server_is_idempotent():
    device = Device.objects.create(hostname="_t_a10_idem", device_type="slb")
    saver = A10VirtualServerSaver()
    parsed = _parsed()

    assert saver.save(device, parsed)[0] == 4
    assert saver.save(device, parsed) == (0, 4)

    assert LtmVirtualServer.objects.filter(device=device).count() == 1
    assert LtmProfile.objects.filter(device=device).count() == 2
    assert LtmPersist.objects.filter(device=device).count() == 1
