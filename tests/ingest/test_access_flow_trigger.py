"""访问流重建的投递触点（ingest.access_flow_trigger）：任务名字符串 send_task、开关语义。

守护三点：

- **按任务名投递**：send_task 收到的第一个参数必须是 ``settings.ACCESS_FLOW_TASK``
  字符串（投递侧不 import analysis——依赖方向 analysis → ingest 单向，这条边界靠
  本测试 + 模块结构守住）；
- **开关语义**：``ACCESS_FLOW_DISPATCH`` 关掉时是静默空操作（conftest 统一置 False，
  否则 PolicySaver 每保存一次就把消息发进真实 Redis）；
- **PolicySaver 触发**：策略落库后必须走到投递（开关开时）。
"""

from types import SimpleNamespace

import pytest

from assets.models import Device


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _patch_send(monkeypatch, settings) -> list:
    """把 trigger 的 celery 句柄换成记账桩，返回 ``(task_name, args)`` 的记录列表。"""
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        "ingest.access_flow_trigger.current_app",
        SimpleNamespace(send_task=lambda name, args=None: calls.append((name, list(args or [])))),
    )
    assert settings.ACCESS_FLOW_TASK == "analysis.rebuild_access_flows", "任务名唯一定义处"
    return calls


# ---------------------------------------------------------------------------
# 投递开关与任务名
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_request_rebuild_sends_task_name_string(settings, monkeypatch):
    """投递物是任务名字符串 + args——不是函数对象，worker 端拿名字查注册表执行"""
    from ingest.access_flow_trigger import request_rebuild

    calls = _patch_send(monkeypatch, settings)

    settings.ACCESS_FLOW_DISPATCH = True
    request_rebuild(7)
    assert calls == [(settings.ACCESS_FLOW_TASK, [7])]


@pytest.mark.django_db
def test_request_rebuild_respects_settings_switch(settings, monkeypatch):
    from ingest.access_flow_trigger import request_rebuild

    calls = _patch_send(monkeypatch, settings)

    settings.ACCESS_FLOW_DISPATCH = False
    request_rebuild(7)
    assert calls == [], "开关关掉时是静默空操作"

    settings.ACCESS_FLOW_DISPATCH = True
    request_rebuild(7)
    assert calls == [(settings.ACCESS_FLOW_TASK, [7])]


# ---------------------------------------------------------------------------
# PolicySaver 触发
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_policy_saver_triggers_rebuild(settings, monkeypatch):
    """PolicySaver 保存成功后要投递重建——触发点本身（开关开时必须发出）"""
    from ingest.savers.firewall import PolicySaver

    calls = _patch_send(monkeypatch, settings)
    settings.ACCESS_FLOW_DISPATCH = True

    device = _device("_t_as_trigger")
    PolicySaver().save(
        device,
        {"rules": [{"rule_id": "1", "action": "permit", "src-ip": ["192.168.1.1"], "dst-host": ["10.0.0.1"]}]},
    )

    assert calls == [(settings.ACCESS_FLOW_TASK, [device.pk])]


@pytest.mark.django_db
def test_policy_saver_dispatch_is_off_by_default_in_tests(monkeypatch, settings):
    """conftest 的 autouse 开关必须拦掉真实投递（否则测试会把消息发进本机 Redis）"""
    from ingest.savers.firewall import PolicySaver

    calls = _patch_send(monkeypatch, settings)

    device = _device("_t_as_off")
    PolicySaver().save(device, {"rules": [{"rule_id": "1", "action": "permit", "dst-host": ["10.0.0.1"]}]})

    assert calls == [], "默认开关是关的，PolicySaver 不该发出投递"
