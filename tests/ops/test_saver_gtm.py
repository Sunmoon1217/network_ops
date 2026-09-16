"""GTM Saver 测试。

GTM 侧的 Saver 走「Saver 调用序列化器」的路径（`BaseSaver.upsert`），
这里既验证入库结果，也验证字段映射与模板产出名一致。
"""

import pytest

from assets.models import Device, GtmDatacenter, GtmPool, GtmServer, GtmVServer, GtmWideip
from ops.savers.lb import GtmDatacenterSaver, GtmPoolSaver, GtmServerSaver, GTMWideipSaver


@pytest.mark.django_db
def test_gtm_datacenter_upsert():
    """单条产出（dict）与多条产出（list）都要能入库，且第二次是更新而非新增"""
    device = Device.objects.create(hostname="_t_gtm_dc", device_type="gslb")
    saver = GtmDatacenterSaver()

    assert saver.save(device, {"datacenters": {"name": "DC-BJ"}}) == (1, 0)
    assert GtmDatacenter.objects.get(device=device).name == "DC-BJ"

    assert saver.save(device, {"datacenters": [{"name": "DC-BJ"}]}) == (0, 1)
    assert GtmDatacenter.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_gtm_server_saves_virtual_servers():
    """servers 的子 group virtual_servers 要落到 GtmVServer 表"""
    device = Device.objects.create(hostname="_t_gtm_srv", device_type="gslb")
    parsed = {
        "servers": {
            "server_name": "/Common/DC-BJ-SRV",
            "datacenter": "/Common/DC-BJ",
            "server_monitor": "/Common/icmp",
            "server_type": "bigip",
            "virtual_servers": [
                {"vs_name": "vs_web", "vs_address": "10.0.0.1", "vs_port": "443", "vs_monitor": "/Common/tcp"},
                {"vs_name": "vs_app", "vs_address": "10.0.0.2", "vs_port": "80"},
            ],
        }
    }

    created, updated = GtmServerSaver().save(device, parsed)
    assert (created, updated) == (3, 0)  # 1 个 server + 2 个 vserver

    server = GtmServer.objects.get(device=device)
    assert (server.name, server.datacenter, server.monitor, server.server_type) == (
        "/Common/DC-BJ-SRV",
        "/Common/DC-BJ",
        "/Common/icmp",
        "bigip",
    )

    vservers = GtmVServer.objects.filter(device=device, server=server)
    assert vservers.count() == 2
    assert vservers.get(name="vs_web").port == "443"
    assert vservers.get(name="vs_app").ip_address == "10.0.0.2"


@pytest.mark.django_db
def test_gtm_pool_members_go_to_json():
    """pools 的成员落 JSON 字段，带横线的模板键名要正确对应模型字段"""
    device = Device.objects.create(hostname="_t_gtm_pool", device_type="gslb")
    parsed = {
        "pools": {
            "pool_name": "pool_web",
            "pool_type": "A",
            "preferred": "round-robin",
            "alternate-mode": "global-availability",
            "fallback-mode": "return-to-dns",
            "fallback-ip": "10.0.0.9",
            "pool_monitor": "/Common/http",
            "ttl": "30",
            "members": [
                {
                    "server_name": "/Common/s1",
                    "vs_name": "vs_web",
                    "member_order": "0",
                    "member_ratio": "2",
                },
            ],
        }
    }

    assert GtmPoolSaver().save(device, parsed) == (1, 0)

    pool = GtmPool.objects.get(device=device)
    assert pool.name == "pool_web"
    assert pool.lb_mode == "round-robin"
    assert pool.alternate_mode == "global-availability"
    assert pool.fallback_mode == "return-to-dns"
    assert pool.fallback_ip == "10.0.0.9"
    assert pool.ttl == 30
    assert pool.monitor == ["/Common/http"]
    assert pool.members == [
        {
            "server": "/Common/s1",
            "vserver": "vs_web",
            "status": "enabled",
            "order": 0,
            "ratio": 2,
            "monitor": "",
        }
    ]


@pytest.mark.django_db
def test_gtm_pool_defaults_when_template_omits_optional_keys():
    """模板里的 default() 已给值，但缺字段时也要有兜底，且空 fallback-ip 不能进 payload"""
    device = Device.objects.create(hostname="_t_gtm_pool_min", device_type="gslb")

    assert GtmPoolSaver().save(device, {"pools": {"pool_name": "pool_min"}}) == (1, 0)

    pool = GtmPool.objects.get(device=device)
    assert pool.lb_mode == "round-robin"
    assert pool.alternate_mode == "round-robin"
    assert pool.fallback_mode == "return-to-dns"
    assert pool.ttl == 30
    assert pool.fallback_ip is None
    assert pool.members == []


@pytest.mark.django_db
def test_gtm_pool_status_maps_to_is_active():
    """模板的 pool_status 是 enabled/disabled 文本，要映射到布尔字段"""
    device = Device.objects.create(hostname="_t_gtm_pool_st", device_type="gslb")

    GtmPoolSaver().save(device, {"pools": {"pool_name": "p_off", "pool_status": "disabled"}})
    GtmPoolSaver().save(device, {"pools": {"pool_name": "p_on", "pool_status": "enabled"}})

    assert GtmPool.objects.get(device=device, name="p_off").is_active is False
    assert GtmPool.objects.get(device=device, name="p_on").is_active is True


@pytest.mark.django_db
def test_gtm_wideip_reads_template_field_names():
    """wideip_type / wideip_lbmode 必须落到 rtype / lb_mode（原先取 rtype / lb_mode 恒为空）"""
    device = Device.objects.create(hostname="_t_gtm_wi", device_type="gslb")
    parsed = {
        "wideips": {
            "wideip_name": "www.example.com",
            "wideip_type": "A",
            "wideip_lbmode": "topology",
            "pools": [{"pool_name": "pool_web"}],
        }
    }

    assert GTMWideipSaver().save(device, parsed) == (1, 0)

    wideip = GtmWideip.objects.get(device=device)
    assert wideip.rtype == "A"
    assert wideip.lb_mode == "topology"
    assert wideip.pools == ["pool_web"]


@pytest.mark.django_db
def test_gtm_savers_are_idempotent():
    """同一份解析结果重复入库不得产生重复记录"""
    device = Device.objects.create(hostname="_t_gtm_idem", device_type="gslb")
    parsed = {
        "servers": {
            "server_name": "s1",
            "virtual_servers": [{"vs_name": "vs1", "vs_address": "10.0.0.1"}],
        }
    }
    saver = GtmServerSaver()

    assert saver.save(device, parsed) == (2, 0)
    assert saver.save(device, parsed) == (0, 2)
    assert GtmServer.objects.filter(device=device).count() == 1
    assert GtmVServer.objects.filter(device=device).count() == 1
