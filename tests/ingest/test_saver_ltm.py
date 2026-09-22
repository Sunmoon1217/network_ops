"""LTM 虚拟服务器及其 profiles / rules / persist 的 Saver 测试。

用 F5 解析器的**真实产出**驱动：这三个子表的数据嵌在 ``virtuals`` 里，
且 profiles / rules / persist 三种形态各不相同（list-of-dict / dict-with-list / dict）。

F5 的模板产出一律带 ``/Common/`` 分区前缀，Saver 负责剥成叶子名（``_leaf``），
使 ``LtmVirtualServer.pool`` 与 ``LtmPool.name`` 这类关联两侧写法一致。
剥前缀**不能**用 ``lstrip("/Common/")``：它按字符集剥离，会把 ``cookie`` 削成 ``ookie``。
"""

import pytest

from assets.models import (
    Device,
    LtmIRule,
    LtmPersist,
    LtmPool,
    LtmPoolMember,
    LtmProfile,
    LtmSNAT,
    LtmVirtualServer,
)
from ingest.parsers.factory import ParserFactory
from ingest.savers.lb import LBPoolSaver, LBSnatSaver, LBVirtualServerSaver

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

F5_POOL = """ltm pool /Common/pool_web {
    load-balancing-mode least-connections-member
    monitor /Common/http
    members {
        /Common/node_a:80 {
            address 10.0.0.1
        }
        /Common/node_b:8080 {
            address 10.0.0.2
        }
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
    assert vs.name == "vs_web"
    assert vs.vs_address == "10.0.0.1"
    assert vs.vs_port == "443"
    assert vs.snat_pool == "snatpool"
    assert vs.persist == "cookie"
    assert vs.profiles == ["http", "tcp"]


@pytest.mark.django_db
def test_rules_are_flat_not_nested():
    """模板产出 rules 是 {'name': [...]}，拉平后不能出现嵌套 list"""
    device = Device.objects.create(hostname="_t_ltm_rules", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    vs = LtmVirtualServer.objects.get(device=device)
    assert vs.rules == ["irule_redirect"]
    assert LtmIRule.objects.get(device=device).name == "irule_redirect"


@pytest.mark.django_db
def test_profiles_type_from_basename_and_raw_keeps_source():
    """profile 的 type 取路径末段；raw 里留档来源 virtual server（用剥前缀后的名字）"""
    device = Device.objects.create(hostname="_t_ltm_prof", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    profiles = {profile.name: profile for profile in LtmProfile.objects.filter(device=device)}
    assert set(profiles) == {"http", "tcp"}
    assert profiles["http"].type == "http"
    assert profiles["tcp"].type == "tcp"
    assert profiles["http"].raw["virtual_server"] == "vs_web"
    # raw 保留模板原始产出，便于对照模板排查
    assert profiles["http"].raw["name"] == "/Common/http"


@pytest.mark.django_db
def test_persist_recorded_with_type():
    device = Device.objects.create(hostname="_t_ltm_persist", device_type="slb")
    LBVirtualServerSaver().save(device, _parsed())

    persist = LtmPersist.objects.get(device=device)
    assert persist.name == "cookie"
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
    assert LtmProfile.objects.get(device=device).raw["virtual_server"] == "vs2"


@pytest.mark.django_db
def test_virtual_without_sub_tables_still_saves():
    """没有 profiles / rules / persist 的 virtual 也不能报错"""
    device = Device.objects.create(hostname="_t_ltm_bare", device_type="slb")
    parsed = {"virtuals": {"name": "/Common/vs_bare", "vs_address": "10.0.0.9", "vs_port": "8080"}}

    assert LBVirtualServerSaver().save(device, parsed) == (1, 0)
    assert LtmVirtualServer.objects.get(device=device).profiles == []


@pytest.mark.django_db
def test_pool_and_members_drop_common_prefix():
    """池名 / 监视器 / 成员名都要剥前缀，成员挂在剥前缀后的池名下"""
    device = Device.objects.create(hostname="_t_ltm_pool", device_type="slb")
    parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(F5_POOL)

    assert LBPoolSaver().save(device, parsed) == (1, 0)

    pool = LtmPool.objects.get(device=device)
    assert pool.name == "pool_web"
    assert pool.monitors == ["http"]
    assert pool.mode == "least-connections-member"

    members = {m.name: m for m in LtmPoolMember.objects.filter(device=device, pool_name=pool.name)}
    assert set(members) == {"node_a", "node_b"}
    assert members["node_a"].address == "10.0.0.1"
    assert members["node_a"].port == "80"
    assert members["node_b"].port == "8080"
    # 池名与卡片关联两侧保持一致
    assert LtmPoolMember.objects.filter(device=device, pool_name="pool_web").count() == 2


@pytest.mark.django_db
def test_snat_name_and_address_drop_common_prefix():
    """snat pool 的名字与地址都可能是 /Common/xxx 形态"""
    device = Device.objects.create(hostname="_t_ltm_snat", device_type="slb")

    assert LBSnatSaver().save(device, {"snat_pools": {"name": "/Common/snat1", "address": "/Common/1.1.1.1"}}) == (
        1,
        0,
    )

    snat = LtmSNAT.objects.get(device=device)
    assert snat.name == "snat1"
    assert snat.address == "1.1.1.1"


@pytest.mark.django_db
def test_no_common_prefix_leaks_across_ltm_columns():
    """整条链路跑完，LTM 各表的**规范列**里不应残留任何 ``/Common/``。

    ``LtmProfile.raw`` / ``LtmPersist.raw`` 是模板产出留档，刻意保留原始写法，不在此列。
    """
    device = Device.objects.create(hostname="_t_ltm_leak", device_type="slb")
    parser = ParserFactory.get_parser_by_keys("F5", "slb")
    both = parser.parse(F5_POOL + F5_VIRTUAL)

    LBPoolSaver().save(device, both)
    LBVirtualServerSaver().save(device, both)

    columns = {
        "LtmPool.name": LtmPool.objects.filter(device=device).values_list("name", flat=True),
        "LtmPoolMember.name": LtmPoolMember.objects.filter(device=device).values_list("name", flat=True),
        "LtmPoolMember.pool_name": LtmPoolMember.objects.filter(device=device).values_list("pool_name", flat=True),
        "LtmVirtualServer.name": LtmVirtualServer.objects.filter(device=device).values_list("name", flat=True),
        "LtmVirtualServer.pool": LtmVirtualServer.objects.filter(device=device).values_list("pool", flat=True),
        "LtmVirtualServer.snat_pool": LtmVirtualServer.objects.filter(device=device).values_list(
            "snat_pool", flat=True
        ),
        "LtmVirtualServer.persist": LtmVirtualServer.objects.filter(device=device).values_list("persist", flat=True),
        "LtmProfile.name": LtmProfile.objects.filter(device=device).values_list("name", flat=True),
        "LtmProfile.type": LtmProfile.objects.filter(device=device).values_list("type", flat=True),
        "LtmIRule.name": LtmIRule.objects.filter(device=device).values_list("name", flat=True),
        "LtmPersist.name": LtmPersist.objects.filter(device=device).values_list("name", flat=True),
        "LtmPersist.type": LtmPersist.objects.filter(device=device).values_list("type", flat=True),
    }

    leaked = {name: [v for v in values if v and "/" in v] for name, values in columns.items()}
    leaked = {name: values for name, values in leaked.items() if values}
    assert not leaked, f"以下列仍残留分区前缀: {leaked}"

    # 列表字段也要检查（JSONField 不能直接用 values_list 拍平判断）
    vs = LtmVirtualServer.objects.get(device=device)
    assert vs.profiles == ["http", "tcp"]
    assert vs.rules == ["irule_redirect"]
    assert LtmPool.objects.get(device=device).monitors == ["http"]


# ---------- 池成员的设备作用域（LtmPoolMember 继承 ConfigBase 后的约束） ----------


def _pool_config(pool_name: str = "pool_web", members: str = "", monitor: bool = True) -> str:
    """拼一段 F5 pool 配置；members 直接内联以便控制成员形态"""
    body = [
        "    load-balancing-mode least-connections-member",
        "    monitor /Common/http" if monitor else "",
        "    members {",
        members,
        "    }",
    ]
    return f"ltm pool /Common/{pool_name} {{\n" + "\n".join(line for line in body if line) + "\n}\n"


@pytest.mark.django_db
def test_same_pool_name_on_two_devices_does_not_mix():
    """两台设备上的同名池各自保存成员，互不覆盖也互不删除"""
    dev_a = Device.objects.create(hostname="_t_ltm_scope_a", device_type="slb")
    dev_b = Device.objects.create(hostname="_t_ltm_scope_b", device_type="slb")
    parser = ParserFactory.get_parser_by_keys("F5", "slb")
    saver = LBPoolSaver()

    cfg_a = _pool_config(members="        /Common/node_a:80 {\n            address 10.0.0.1\n        }")
    cfg_b = _pool_config(members="        /Common/node_b:80 {\n            address 10.0.0.2\n        }")

    saver.save(dev_a, parser.parse(cfg_a))
    saver.save(dev_b, parser.parse(cfg_b))

    # 各自一条，互不干扰
    assert LtmPoolMember.objects.filter(device=dev_a).count() == 1
    assert LtmPoolMember.objects.filter(device=dev_b).count() == 1
    assert LtmPoolMember.objects.get(device=dev_a).name == "node_a"
    assert LtmPoolMember.objects.get(device=dev_b).name == "node_b"

    # 再存一次 A：不能把 B 的成员删掉（旧实现按 pool_name 全局删就会误删）
    saver.save(dev_a, parser.parse(cfg_a))
    assert LtmPoolMember.objects.filter(device=dev_b).count() == 1
    assert LtmPoolMember.objects.get(device=dev_b).name == "node_b"


@pytest.mark.django_db
def test_deleting_device_cascades_to_members():
    """device 是外键，删设备要级联删掉池成员（此前会留下孤儿）"""
    device = Device.objects.create(hostname="_t_ltm_cascade", device_type="slb")
    parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(F5_POOL)
    LBPoolSaver().save(device, parsed)

    assert LtmPoolMember.objects.filter(device=device).count() == 2

    device.delete()

    assert LtmPoolMember.objects.count() == 0


@pytest.mark.django_db
def test_empty_members_clears_stale_rows():
    """池还在但成员被清空时，旧成员不应残留"""
    device = Device.objects.create(hostname="_t_ltm_clear", device_type="slb")
    parser = ParserFactory.get_parser_by_keys("F5", "slb")
    saver = LBPoolSaver()
    with_members = _pool_config(members="        /Common/node_a:80 {\n            address 10.0.0.1\n        }")

    saver.save(device, parser.parse(with_members))
    assert LtmPoolMember.objects.filter(device=device).count() == 1

    saver.save(device, parser.parse(_pool_config()))
    assert LtmPoolMember.objects.filter(device=device).count() == 0


@pytest.mark.django_db
def test_same_node_on_two_ports_is_kept():
    """同一节点在两个端口上做成员是合法的，唯一约束带 port 才不会误杀"""
    device = Device.objects.create(hostname="_t_ltm_ports", device_type="slb")
    members = "\n".join(
        [
            "        /Common/node_a:80 {",
            "            address 10.0.0.1",
            "        }",
            "        /Common/node_a:8080 {",
            "            address 10.0.0.1",
            "        }",
        ]
    )
    parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(_pool_config(members=members))

    LBPoolSaver().save(device, parsed)

    rows = LtmPoolMember.objects.filter(device=device).order_by("port")
    assert [row.name for row in rows] == ["node_a", "node_a"]
    assert [row.port for row in rows] == ["80", "8080"]


@pytest.mark.django_db
def test_duplicate_members_in_one_config_are_collapsed():
    """同一份配置里重复出现的同一成员（同 name + 同 port）只落一条，不触发唯一约束"""
    device = Device.objects.create(hostname="_t_ltm_dup", device_type="slb")
    one = "        /Common/node_a:80 {\n            address 10.0.0.1\n        }"
    parsed = ParserFactory.get_parser_by_keys("F5", "slb").parse(_pool_config(members=f"{one}\n{one}"))

    LBPoolSaver().save(device, parsed)

    assert LtmPoolMember.objects.filter(device=device).count() == 1


@pytest.mark.django_db
def test_unique_constraint_rejects_duplicate_member():
    """数据库层面兜底：(device, pool_name, name, port) 唯一"""
    from django.db import IntegrityError, transaction

    device = Device.objects.create(hostname="_t_ltm_uniq", device_type="slb")
    LtmPoolMember.objects.create(device=device, pool_name="p", name="n", address="10.0.0.1", port="80")

    with pytest.raises(IntegrityError), transaction.atomic():
        LtmPoolMember.objects.create(device=device, pool_name="p", name="n", address="10.0.0.2", port="80")

    # 换端口即合法
    LtmPoolMember.objects.create(device=device, pool_name="p", name="n", address="10.0.0.1", port="8080")
    assert LtmPoolMember.objects.filter(device=device).count() == 2
