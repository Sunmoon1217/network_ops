"""策略展开（analysis.policy_expand）：归一化、笛卡尔积、合并入库、上下文摘除与重建。

守护的语义：

- 唯一键**十元组**的归一化规则（四形态地址 + 三段服务 + action，NULL 哨兵坑不存在）；
- 同一键跨设备/跨策略聚合进一行 ``contexts``（键带策略主键，同设备重复策略不互覆盖）；
- 同五元组按 action 分行（allow / deny 是两条独立的流——「遗漏」与「多开」审计各对照一行）；
- 先查后合并的幂等性（跑两遍与跑一遍一致）——这是 acks_late 重放不脏数据的地基；
- 摘除按设备前缀剥离、空行删除；整设备重建 = 摘旧 + 写新，同一事务。
"""

import ipaddress
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from analysis.models import AccessFlow
from analysis.policy_expand import (
    ANY,
    ANY_ADDR,
    collect_device_flows,
    expand_policy,
    rebuild_device,
    remove_device_context,
    service_parts,
    upsert_flows,
)
from assets.models import AddressBook, Device, Policy, Service

# ---------------------------------------------------------------------------
# 造数据助手
# ---------------------------------------------------------------------------


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _host(device: Device, ip: str) -> AddressBook:
    return AddressBook.objects.create(device=device, name=f"h-{ip}", address_type="host", ip_address=ip)


def _subnet(device: Device, cidr: str) -> AddressBook:
    network = ipaddress.ip_network(cidr, strict=False)
    return AddressBook.objects.create(
        device=device,
        name=f"s-{cidr}",
        address_type="subnet",
        ip_address=str(network.network_address),
        ip_netmask=network.prefixlen,
    )


def _range(device: Device, start: str, end: str) -> AddressBook:
    return AddressBook.objects.create(
        device=device, name=f"r-{start}-{end}", address_type="range", ip_start=start, ip_end=end
    )


def _group(device: Device, name: str, children: tuple[AddressBook, ...] = ()) -> AddressBook:
    group = AddressBook.objects.create(device=device, name=name, address_type="addressbook")
    for child in children:
        AddressBook.objects.filter(pk=child.pk).update(parent=group)
    return group


def _service(device: Device, name: str, protocol: str = "tcp", port: str = "", port2: str = "") -> Service:
    return Service.objects.create(device=device, name=name, protocol=protocol, port=port, port2=port2)


def _policy(device: Device, pid: str, *, src=(), dst=(), svc=(), order: int = 0) -> Policy:
    policy = Policy.objects.create(device=device, policy_id=pid, order=order, name=f"p-{pid}")
    if src:
        policy.source_addresses.set(src)
    if dst:
        policy.destination_addresses.set(dst)
    if svc:
        policy.services.set(svc)
    return policy


def _key(row: AccessFlow) -> tuple:
    return (
        row.src_ip,
        row.src_prefix,
        row.src_range_end,
        row.dst_ip,
        row.dst_prefix,
        row.dst_range_end,
        row.protocol,
        row.port,
        row.port2,
        row.action,
    )


# ---------------------------------------------------------------------------
# 归一化：唯一键的十个字段
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_host_subnet_range_forms_map_to_expected_key():
    """单 IP / 子网 / 范围三种形态各自落到 ip/prefix/range_end 的预期组合"""
    device = _device("_t_af_form")
    host = _host(device, "10.0.0.1")
    subnet, rng = _subnet(device, "10.0.0.0/24"), _range(device, "10.1.1.1", "10.1.1.9")
    service = _service(device, "web", protocol="tcp", port="80", port2="8080")
    _policy(device, "1", src=(host,), dst=(subnet, rng), svc=(service,))
    rebuild_device(device)

    keys = {_key(row) for row in AccessFlow.objects.filter(device_ids__contains=[device.pk])}
    # 源=单 IP：前缀取满 32；目的=子网：前缀 24；目的=范围：prefix 0 + range_end 非空
    assert ("10.0.0.1", 32, "", "10.0.0.0", 24, "", "tcp", "80", "8080", "allow") in keys
    assert ("10.0.0.1", 32, "", "10.1.1.1", 0, "10.1.1.9", "tcp", "80", "8080", "allow") in keys


@pytest.mark.django_db
def test_ipv6_spelling_variants_share_one_key():
    """IPv6 大小写 / 展开写法必须归一到同一个键（否则跨设备聚合直接失效）"""
    device = _device("_t_af_v6")
    src = _host(device, "2001:DB8::1")
    also = _host(device, "2001:db8:0000:0000:0000:0000:0000:0001")
    dst = _host(device, "2001:db8::2")
    _policy(device, "1", src=(src, also), dst=(dst,))
    rebuild_device(device)

    rows = list(AccessFlow.objects.filter(device_ids__contains=[device.pk]))
    assert len(rows) == 1, "两种写法是同一条流，不该落两行"
    assert rows[0].src_ip == "2001:db8::1"


@pytest.mark.django_db
def test_empty_dimensions_fall_back_to_any():
    """三个维度都空 → 任意×任意×任意；空值不走 NULL，走哨兵（约束仍然生效）"""
    device = _device("_t_af_any")
    _policy(device, "1")
    rebuild_device(device)

    row = AccessFlow.objects.get(device_ids__contains=[device.pk])
    assert (row.src_ip, row.src_prefix, row.src_range_end) == ANY_ADDR
    assert (row.dst_ip, row.dst_prefix, row.dst_range_end) == ANY_ADDR
    assert (row.protocol, row.port, row.port2) == (ANY, "", "")


@pytest.mark.django_db
def test_addressbook_group_expands_members_and_empty_group_is_any():
    """组展开成员；空组（占位记录）按 any——宁可保守也不静默丢策略"""
    device = _device("_t_af_group")
    m1, m2 = _host(device, "192.0.2.1"), _host(device, "192.0.2.2")
    filled = _group(device, "web-servers", (m1, m2))
    empty = _group(device, "placeholder")
    dst = _host(device, "10.0.0.1")
    _policy(device, "1", src=(filled, empty), dst=(dst,))
    rebuild_device(device)

    src_ips = {row.src_ip for row in AccessFlow.objects.filter(device_ids__contains=[device.pk])}
    assert src_ips == {"192.0.2.1", "192.0.2.2", "0.0.0.0"}, "空组成员缺席时按 any 兜底"


@pytest.mark.django_db
def test_duplicate_policies_on_same_device_keep_separate_contexts():
    """同一设备上内容重复的两条策略：contexts 各占一键（多开审计的数据来源），
    device_ids 去重成单元素、policy_ids 记两条"""
    device = _device("_t_af_dup")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    svc = _service(device, "http", protocol="tcp", port="80")
    first = _policy(device, "100", src=(src,), dst=(dst,), svc=(svc,), order=0)
    second = _policy(device, "101", src=(src,), dst=(dst,), svc=(svc,), order=1)

    rebuild_device(device)

    row = AccessFlow.objects.get()
    assert set(row.contexts) == {f"{device.pk}:{first.pk}", f"{device.pk}:{second.pk}"}
    assert row.device_ids == [device.pk], "同一台设备只该出现一次"
    assert sorted(row.policy_ids) == sorted([first.pk, second.pk])


def test_service_parts_normalization():
    """服务三段：icmp 无端口两段皆空、前导零归一、port2 与 port 相同视作单端口"""
    plain = Service(device=None, protocol="TCP", port="080", port2="")
    assert service_parts(plain) == ("tcp", "80", "")

    same = Service(device=None, protocol="tcp", port="443", port2="443")
    assert service_parts(same) == ("tcp", "443", "")

    span = Service(device=None, protocol="udp", port="8000", port2="8080")
    assert service_parts(span) == ("udp", "8000", "8080")

    icmp = Service(device=None, protocol="icmp", port="", port2="")
    assert service_parts(icmp) == ("icmp", "", "")


def test_protocol_choices_match_service_model():
    """AccessFlow 的 protocol 取值必须与 assets.Service 同一套（两边各自声明，防漂移）"""
    service_choices = set(Service._meta.get_field("protocol").choices)
    assert set(AccessFlow.PROTOCOL_CHOICES) == service_choices


# ---------------------------------------------------------------------------
# 展开与合并
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_expand_is_cartesian_product_with_single_context():
    device = _device("_t_af_cart")
    srcs = (_host(device, "10.0.0.1"), _host(device, "10.0.0.2"))
    dsts = (_host(device, "10.0.1.1"), _host(device, "10.0.1.2"))
    svc = _service(device, "http", protocol="tcp", port="80")
    policy = _policy(device, "1", src=srcs, dst=dsts, svc=(svc,))

    flows = expand_policy(policy)

    assert len(flows) == 4  # 2 × 2 × 1
    context_key = f"{device.pk}:{policy.pk}"
    assert all(list(flow["contexts"]) == [context_key] for flow in flows)
    context = flows[0]["contexts"][context_key]
    assert context["hostname"] == device.hostname
    assert context["policy_id"] == "1"
    assert context["action"] == "allow"


@pytest.mark.django_db
def test_upsert_merges_same_key_across_devices():
    """跨设备同键聚合成一行：contexts 两条、device_ids 两台——聚合审计的前提"""
    key = ("10.0.0.1", 32, "", "10.0.0.2", 32, "", "tcp", "80", "", "allow")
    flows = []
    for index, hostname in enumerate(("_t_af_m1", "_t_af_m2"), start=1):
        device = _device(hostname)
        context = {
            "device_id": device.pk,
            "hostname": hostname,
            "policy_pk": index,
            "policy_id": str(index),
            "name": "p",
            "action": "allow",
            "order": 0,
            "enabled": True,
        }
        flows.append({"key": key, "contexts": {f"{device.pk}:{index}": context}})

    assert upsert_flows(flows) == (1, 0)
    row = AccessFlow.objects.get()
    assert len(row.contexts) == 2
    assert len(row.device_ids) == 2, "两台设备都要记进冗余数组"
    assert len(row.policy_ids) == 2


@pytest.mark.django_db
def test_upsert_is_idempotent():
    """重复投递（acks_late 重放）必须收敛：第二遍既不新建也不更新"""
    device = _device("_t_af_idem")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    svc = _service(device, "http", protocol="tcp", port="80")
    _policy(device, "1", src=(src,), dst=(dst,), svc=(svc,))
    flows = collect_device_flows(device)

    first = upsert_flows(flows)
    second = upsert_flows(flows)

    assert first[0] == 1
    assert second == (0, 0), "同一份数据再跑一遍不该有变化"
    assert AccessFlow.objects.count() == 1


@pytest.mark.django_db
def test_unique_constraint_rejects_duplicate_key():
    AccessFlow.objects.create(
        src_ip="10.0.0.1",
        src_prefix=32,
        dst_ip="10.0.0.2",
        dst_prefix=32,
        protocol="tcp",
        port="80",
        action="allow",
        contexts={},
        device_ids=[],
        policy_ids=[],
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        AccessFlow.objects.create(
            src_ip="10.0.0.1",
            src_prefix=32,
            dst_ip="10.0.0.2",
            dst_prefix=32,
            protocol="tcp",
            port="80",
            action="allow",
            contexts={},
            device_ids=[],
            policy_ids=[],
        )


@pytest.mark.django_db
def test_unique_constraint_allows_same_key_different_action():
    """十元组约束的核心语义：同五元组的 allow 行与 deny 行**必须**能共存——
    「遗漏」审计拿 allow 行对照应放、「多开」拿 deny 行对照应拒，混一行两审计互斥"""
    AccessFlow.objects.create(
        src_ip="10.0.0.1",
        src_prefix=32,
        dst_ip="10.0.0.2",
        dst_prefix=32,
        protocol="tcp",
        port="80",
        action="allow",
        contexts={},
        device_ids=[],
        policy_ids=[],
    )
    deny = AccessFlow.objects.create(
        src_ip="10.0.0.1",
        src_prefix=32,
        dst_ip="10.0.0.2",
        dst_prefix=32,
        protocol="tcp",
        port="80",
        action="deny",
        contexts={},
        device_ids=[],
        policy_ids=[],
    )
    assert AccessFlow.objects.count() == 2
    assert deny.action == "deny"


# ---------------------------------------------------------------------------
# 摘除与重建
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_remove_device_context_keeps_other_devices_and_deletes_empty_rows():
    device_a, device_b = _device("_t_af_rm_a"), _device("_t_af_rm_b")
    key = ("10.0.0.1", 32, "", "10.0.0.2", 32, "", "tcp", "80", "")
    both = {"a": {"device_id": device_a.pk, "policy_pk": 1}, "b": {"device_id": device_b.pk, "policy_pk": 2}}
    # contexts 键必须带设备前缀：手造一份规范键
    contexts = {f"{device_a.pk}:1": both["a"], f"{device_b.pk}:2": both["b"]}
    shared = AccessFlow.objects.create(
        src_ip=key[0],
        src_prefix=key[1],
        dst_ip=key[3],
        dst_prefix=key[4],
        protocol=key[6],
        port=key[7],
        port2=key[8],
        action="allow",
        contexts=contexts,
        device_ids=[device_a.pk, device_b.pk],
        policy_ids=[1, 2],
    )
    only_a = AccessFlow.objects.create(
        src_ip="192.0.2.1",
        src_prefix=32,
        dst_ip="192.0.2.2",
        dst_prefix=32,
        protocol="tcp",
        port="22",
        action="allow",
        contexts={f"{device_a.pk}:9": {"device_id": device_a.pk, "policy_pk": 9}},
        device_ids=[device_a.pk],
        policy_ids=[9],
    )

    remove_device_context(device_a.pk)

    shared.refresh_from_db()
    assert set(shared.contexts) == {f"{device_b.pk}:2"}, "B 设备的上下文要保留"
    assert shared.device_ids == [device_b.pk]
    assert shared.policy_ids == [2]
    assert not AccessFlow.objects.filter(pk=only_a.pk).exists(), "只剩 A 的行要整行删除"


@pytest.mark.django_db
def test_remove_device_context_does_not_touch_other_device_ids():
    """前缀带冒号：设备 1 的摘除不能误伤设备 11"""
    device_1, device_11 = _device("_t_af_rm_1"), _device("_t_af_rm_11")
    row = AccessFlow.objects.create(
        src_ip="10.0.0.1",
        src_prefix=32,
        dst_ip="10.0.0.2",
        dst_prefix=32,
        protocol="tcp",
        port="80",
        action="allow",
        contexts={
            f"{device_1.pk}:1": {"device_id": device_1.pk, "policy_pk": 1},
            f"{device_11.pk}:2": {"device_id": device_11.pk, "policy_pk": 2},
        },
        device_ids=[device_1.pk, device_11.pk],
        policy_ids=[1, 2],
    )
    # 让两个设备 id 满足前缀关系的形态：1 与 1x——这里 pk 未必恰好如此，键前缀语义
    # 由 f"{id}:" 保证，用任意 pk 也应正确剥离
    remove_device_context(device_1.pk)

    row.refresh_from_db()
    assert set(row.contexts) == {f"{device_11.pk}:2"}
    assert device_11.pk in row.device_ids


@pytest.mark.django_db
def test_rebuild_device_drops_stale_flows_after_policy_change():
    """策略改了：重建后旧键的行消失、新键出现（先摘后写的整设备语义）"""
    device = _device("_t_af_stale")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    svc = _service(device, "http", protocol="tcp", port="80")
    _policy(device, "1", src=(src,), dst=(dst,), svc=(svc,))
    rebuild_device(device)
    assert AccessFlow.objects.count() == 1

    # 换一套地址（同策略 pk）
    policy = Policy.objects.get(device=device, policy_id="1")
    policy.source_addresses.set([_host(device, "172.16.0.1")])
    rebuild_device(device)

    rows = list(AccessFlow.objects.filter(device_ids__contains=[device.pk]))
    assert len(rows) == 1
    assert rows[0].src_ip == "172.16.0.1"


@pytest.mark.django_db
def test_rebuild_device_cleans_up_when_all_policies_removed():
    device = _device("_t_af_clean")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    _policy(device, "1", src=(src,), dst=(dst,))
    rebuild_device(device)
    assert AccessFlow.objects.count() == 1

    Policy.objects.filter(device=device).delete()
    created, updated = rebuild_device(device)

    assert AccessFlow.objects.count() == 0, "设备没有策略时重建等于清理"
    assert (created, updated) == (0, 0)


# ---------------------------------------------------------------------------
# rebuild_access_flows 管理命令
# ---------------------------------------------------------------------------


def _run_command(*args) -> str:
    out = StringIO()
    call_command("rebuild_access_flows", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_command_sync_rebuilds_in_process():
    device = _device("_t_af_cmd")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    svc = _service(device, "http", protocol="tcp", port="80")
    _policy(device, "1", src=(src,), dst=(dst,), svc=(svc,))

    output = _run_command("--device", device.hostname, "--sync")

    assert "sync" in output
    assert AccessFlow.objects.filter(device_ids__contains=[device.pk]).count() == 1


@pytest.mark.django_db
def test_command_dispatches_by_default(monkeypatch):
    device = _device("_t_af_cmd2")
    calls: list[int] = []
    monkeypatch.setattr("ingest.access_flow_trigger.request_rebuild", calls.append)

    _run_command("--device", device.hostname)

    assert calls == [device.pk], "默认模式应逐台投递重建任务"


@pytest.mark.django_db
def test_command_dedupes_repeated_devices(monkeypatch):
    device = _device("_t_af_cmd3")
    calls: list[int] = []
    monkeypatch.setattr("ingest.access_flow_trigger.request_rebuild", calls.append)

    _run_command("--device", device.hostname, "--device", device.hostname)

    assert calls == [device.pk], "同一台设备重复传入只投一次"


@pytest.mark.django_db
def test_command_unknown_device_raises():
    from django.core.management import CommandError

    with pytest.raises(CommandError, match="设备不存在"):
        _run_command("--device", "no-such-host")


# ---------------------------------------------------------------------------
# 服务拆行的端到端（真实模板 → 真实 Saver 顺序 → AccessFlow 两组合）
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_multi_protocol_service_expands_into_two_flow_rows():
    """同名 service 两行（tcp 22 + udp 53）→ Service 两行、策略挂两行、
    AccessFlow 出 tcp/udp **两个组合**——修复前合并成一条 (tcp, "22,53")，
    udp/53 的流整条缺失（审计漏流）。

    走 build_saver_payloads 的真实执行顺序（registry 已保证 ServiceSaver 先于
    PolicySaver——先有稳定行、再挂 M2M）。
    """
    from ingest.parsers.factory import ParserFactory
    from ingest.savers.registry import build_saver_payloads

    device = _device("_t_svc_flow")
    parsed = ParserFactory.get_parser_by_keys("Hillstone", "firewall").parse(
        'service "X-wrapper"\n  tcp dst 22\n  udp dst 53\nexit\n'
        'rule id 1\n  action permit\n  src-ip 10.0.0.1\n  dst-ip 10.0.0.2\n'
        '  service "X-wrapper"\n  name "r1"\nexit\n'
    )
    assert parsed.get("services"), "样例应解析出 services（真实模板路径）"

    payloads = build_saver_payloads("firewall", parsed)
    # 排序保证：被引用的维表（ServiceSaver）必须排在引用方（PolicySaver）之前
    saver_names = [type(saver).__name__ for saver, _ in payloads]
    assert saver_names[0] == "ServiceSaver", f"ServiceSaver 应先跑，实际顺序 {saver_names}"
    for saver, payload in payloads:
        saver.save(device, payload)

    # 1) Service 拆两行
    svc_rows = {(s.protocol, s.port) for s in Service.objects.filter(device=device, name="X-wrapper")}
    assert svc_rows == {("tcp", "22"), ("udp", "53")}

    # 2) 策略挂上全部两行（引用名字 = 挂它的全部端口定义）
    policy = Policy.objects.get(device=device)
    assert policy.services.count() == 2

    # 3) AccessFlow 展开 tcp/udp 两个组合（下游漏流修复的最终证据）
    rebuild_device(device)
    flows = {
        (row.protocol, row.port)
        for row in AccessFlow.objects.filter(device_ids__contains=[device.pk])
    }
    assert flows == {("tcp", "22"), ("udp", "53")}


@pytest.mark.django_db
def test_policy_reference_gets_all_rows_even_when_defined_first():
    """Service 先于 Policy 跑（registry 排序）时，引用拿到的是全部行——
    补充场景：占位逻辑不应发生（真行已存在 → missing 为空 → 无 any 占位混入）"""
    from ingest.savers.registry import build_saver_payloads

    device = _device("_t_svc_noplace")
    parsed = {
        "services": {"DUAL": [{"protocol": "tcp", "port": "80"}, {"protocol": "udp", "port": "80"}]},
        "policies": {
            "policy_id": "1",
            "action": "allow",
            "service": ["DUAL"],
            "src-ip": ["10.0.0.1"],
            "dst-ip": ["10.0.0.2"],
            "name": "r1",
        },
    }
    for saver, payload in build_saver_payloads("firewall", parsed):
        saver.save(device, payload)

    assert Service.objects.filter(device=device, name="DUAL").count() == 2
    assert not Service.objects.filter(device=device, name="DUAL", protocol="any").exists(), (
        "真行已存在时不该再建 any 占位——占位混入会让 AccessFlow 多出一个 any 组合"
    )
    policy = Policy.objects.get(device=device)
    assert policy.services.count() == 2
# ------------------------------------------------------------------------------
# action 进键：同五元组按动作分行
# ------------------------------------------------------------------------------
@pytest.mark.django_db
def test_same_five_tuple_allow_and_deny_land_as_two_rows():
    """真实展开路径：同五元组被 allow 与 deny 策略命中 → 两行、action 各一

    contexts 不混：allow 行只挂 allow 策略的 context（行级 action 恒等于其
    contexts 内各 context 的 action）。
    """
    device = _device("_t_af_action")
    src, dst = _host(device, "10.0.0.1"), _host(device, "10.0.0.2")
    svc = _service(device, "http", protocol="tcp", port="80")
    allow_policy = _policy(device, "1", src=(src,), dst=(dst,), svc=(svc,), order=0)
    deny_policy = _policy(device, "2", src=(src,), dst=(dst,), svc=(svc,), order=1)
    deny_policy.action = "deny"
    deny_policy.save(update_fields=["action"])

    rebuild_device(device)

    rows = list(AccessFlow.objects.filter(device_ids__contains=[device.pk]))
    assert len(rows) == 2, f"allow/deny 必须分行，实际 {len(rows)} 行"
    assert {row.action for row in rows} == {"allow", "deny"}
    # 各行只挂自己动作的 context
    by_action = {row.action: row for row in rows}
    assert set(by_action["allow"].contexts) == {f"{device.pk}:{allow_policy.pk}"}
    assert set(by_action["deny"].contexts) == {f"{device.pk}:{deny_policy.pk}"}
    # 行级 action 恒等于 contexts 内 context 的 action
    for row in rows:
        assert all(ctx["action"] == row.action for ctx in row.contexts.values())


@pytest.mark.django_db
def test_upsert_separates_actions_into_two_rows():
    """直接喂 upsert：同九元组、不同 action 的两条 flow → 两行（键含 action 的直接证据）"""
    base = ("10.0.0.1", 32, "", "10.0.0.2", 32, "", "tcp", "80", "")
    device = _device("_t_af_up_action")
    context = {
        "device_id": device.pk,
        "hostname": device.hostname,
        "policy_pk": 1,
        "policy_id": "1",
        "name": "p",
        "action": "allow",
        "order": 0,
        "enabled": True,
    }
    flows = [
        {"key": (*base, "allow"), "contexts": {f"{device.pk}:1": dict(context, action="allow")}},
        {"key": (*base, "deny"), "contexts": {f"{device.pk}:2": dict(context, policy_pk=2, action="deny")}},
    ]

    assert upsert_flows(flows) == (2, 0)
    assert AccessFlow.objects.count() == 2
