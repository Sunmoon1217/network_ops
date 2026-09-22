"""访问流的 Stream 通道（ops.access_stream）：编解码、单写者入库、投递开关、ACK 语义。

不碰真实 Redis：消息体用生产者的真实路径（collect → encode）构造，处理侧直接调
``handle_message``；消费者命令的 ACK 行为用假 client 验证（成功才 ack、失败留 PEL）。
"""

from types import SimpleNamespace

import pytest

from assets.models import AddressBook, Device, Policy, Service
from ops import access_stream
from ops.access_stream import decode_message, encode_message, handle_message
from ops.management.commands.access_flow_consumer import Command as ConsumerCommand
from ops.policy_expand import collect_device_flows


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _seed_policy(device: Device, pid: str = "1") -> Policy:
    src = AddressBook.objects.create(device=device, name="s", address_type="host", ip_address="10.0.0.1")
    dst = AddressBook.objects.create(device=device, name="d", address_type="host", ip_address="10.0.0.2")
    service = Service.objects.create(device=device, name="web", protocol="tcp", port="80")
    policy = Policy.objects.create(device=device, policy_id=pid, order=0, name=f"p-{pid}")
    policy.source_addresses.set([src])
    policy.destination_addresses.set([dst])
    policy.services.set([service])
    return policy


def _message(device: Device) -> dict[str, str]:
    """走生产者的真实路径造一条消息（collect → encode）"""
    return encode_message(device, collect_device_flows(device))


# ---------------------------------------------------------------------------
# 编解码
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_encode_decode_roundtrip_preserves_keys_and_contexts():
    device = _device("_t_as_rt")
    policy = _seed_policy(device)

    fields = _message(device)
    device_id, flows = decode_message(fields)

    assert device_id == device.pk
    assert len(flows) == 1
    flow = flows[0]
    assert flow["key"] == ("10.0.0.1", 32, "", "10.0.0.2", 32, "", "tcp", "80", "")
    context = flow["contexts"][f"{device.pk}:{policy.pk}"]
    assert context["device_id"] == device.pk
    assert context["hostname"] == device.hostname
    assert context["policy_id"] == "1"


@pytest.mark.django_db
def test_decode_missing_field_raises():
    device = _device("_t_as_bad")
    fields = _message(device)
    del fields["flows"]
    with pytest.raises(ValueError, match="缺少字段"):
        decode_message(fields)


# ---------------------------------------------------------------------------
# 单写者入库语义
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_handle_message_is_idempotent():
    device = _device("_t_as_idem")
    _seed_policy(device)
    fields = _message(device)

    first = handle_message(fields)
    second = handle_message(fields)

    from ops.models import AccessFlow

    assert AccessFlow.objects.count() == 1, "重放不该多出行"
    assert first[0] == 1 and second == (0, 0)


@pytest.mark.django_db
def test_handle_message_replaces_only_its_own_device():
    """消息 A = 设备 A 的完整状态：替换成它不会动设备 B 的上下文，也不删 B 的行"""
    from ops.models import AccessFlow

    device_a, device_b = _device("_t_as_a"), _device("_t_as_b")
    _seed_policy(device_a, "1")
    # B 设备一条**不同键**的流，先入库
    service_b = Service.objects.create(device=device_b, name="ssh", protocol="tcp", port="22")
    src_b = AddressBook.objects.create(device=device_b, name="sb", address_type="host", ip_address="192.0.2.1")
    dst_b = AddressBook.objects.create(device=device_b, name="db", address_type="host", ip_address="192.0.2.2")
    policy_b = Policy.objects.create(device=device_b, policy_id="1", order=0, name="p1")
    policy_b.source_addresses.set([src_b])
    policy_b.destination_addresses.set([dst_b])
    policy_b.services.set([service_b])
    handle_message(_message(device_b))

    # A 的消息（空状态：删光 A 的策略）重放，不该影响 B
    Policy.objects.filter(device=device_a).delete()
    handle_message(_message(device_a))

    remaining = list(AccessFlow.objects.all())
    assert len(remaining) == 1
    assert remaining[0].device_ids == [device_b.pk]


@pytest.mark.django_db
def test_handle_message_clears_device_when_no_policies_left():
    from ops.models import AccessFlow

    device = _device("_t_as_clear")
    _seed_policy(device)
    handle_message(_message(device))
    assert AccessFlow.objects.count() == 1

    Policy.objects.filter(device=device).delete()
    handle_message(_message(device))

    assert AccessFlow.objects.count() == 0, "空消息 = 清掉该设备的全部残留上下文"


# ---------------------------------------------------------------------------
# 投递开关
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_request_rebuild_respects_settings_switch(settings, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr("ops.tasks.rebuild_access_flows", SimpleNamespace(delay=calls.append))

    settings.ACCESS_FLOW_DISPATCH = False
    access_stream.request_rebuild(7)
    assert calls == []

    settings.ACCESS_FLOW_DISPATCH = True
    access_stream.request_rebuild(7)
    assert calls == [7]


@pytest.mark.django_db
def test_policy_saver_triggers_rebuild(settings, monkeypatch):
    """PolicySaver 保存成功后要投递重建——触发点本身（开关关掉时为静默空操作）"""
    from ops.savers.firewall import PolicySaver

    calls: list[int] = []
    monkeypatch.setattr("ops.tasks.rebuild_access_flows", SimpleNamespace(delay=calls.append))
    settings.ACCESS_FLOW_DISPATCH = True

    device = _device("_t_as_trigger")
    PolicySaver().save(
        device,
        {"rules": [{"rule_id": "1", "action": "permit", "src-ip": ["192.168.1.1"], "dst-host": ["10.0.0.1"]}]},
    )

    assert calls == [device.pk]


@pytest.mark.django_db
def test_policy_saver_dispatch_is_off_by_default_in_tests(monkeypatch):
    """conftest 的 autouse 开关必须拦掉真实投递（否则测试会把消息发进本机 Redis）"""
    from ops.savers.firewall import PolicySaver

    calls: list[int] = []
    monkeypatch.setattr("ops.tasks.rebuild_access_flows", SimpleNamespace(delay=calls.append))

    device = _device("_t_as_off")
    PolicySaver().save(device, {"rules": [{"rule_id": "1", "action": "permit", "dst-host": ["10.0.0.1"]}]})

    assert calls == [], "默认开关是关的，PolicySaver 不该发出投递"


# ---------------------------------------------------------------------------
# 消费者命令的 ACK 语义
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self):
        self.acked: list[str] = []

    def xack(self, stream: str, group: str, message_id: str) -> None:
        self.acked.append(message_id)


def test_consumer_acks_after_successful_handle(monkeypatch):
    monkeypatch.setattr("ops.access_stream.handle_message", lambda fields: (1, 2))
    client = _FakeClient()

    ConsumerCommand()._process(client, "100-0", {"flows": b"[]"})

    assert client.acked == ["100-0"], "入库成功才 ack"


def test_consumer_keeps_message_on_failure(monkeypatch):
    """处理失败不 ack：消息留在 PEL 等 XAUTOCLAIM 重投（幂等重放不脏数据）"""

    def _boom(fields):
        raise RuntimeError("db down")

    monkeypatch.setattr("ops.access_stream.handle_message", _boom)
    client = _FakeClient()

    ConsumerCommand()._process(client, "100-0", {"flows": b"[]"})

    assert client.acked == []
