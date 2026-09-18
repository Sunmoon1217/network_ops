"""路由采集接口：保存路径的回归测试。

历史缺陷（实测）：两个端点建 ``Route`` 时只传 ``vrf``、不传 ``device``，而
``Route.device`` 自 migration 0023 起是非空外键——于是每条插入都撞
``NotNullViolation``，异常被 ``except Exception`` 吞进 ``errors``，接口仍然返回
``success: true`` 与 ``created: 0``；更糟的是 ``delete()`` 在循环**之前**，所以真实
行为是「报成功、把该 VRF 原有路由删光、一条都没写回」。

``route_collect`` 走 TTP 模板解析，而 ``running/route.ttp`` 目前自身解析失败
（``ParseError: mismatched tag``，属本轮之外的既有问题），所以那条用例用假 parser
只覆盖「保存」这一段。
"""

import pytest
from rest_framework.test import APIClient

from assets.models import Device, Route, Vrf
from core.models import User

RAW_URL = "/api/trace/route-collect-raw/"
API_URL = "/api/trace/route-collect/"

RAW_TEXT = """C    10.1.1.0/24 is directly connected, GigabitEthernet0/1
S    10.2.0.0/16 [1/0] via 10.1.1.254
S    10.3.0.0/16 [1/0] via 10.1.1.254
"""


@pytest.fixture
def client(db):
    """这两个端点要求登录（IsAuthenticated）。"""
    user = User.objects.create_user(username="_t_route_api", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def device(db):
    return Device.objects.create(hostname="_t_route_dev", device_type="switch")


def _seed(vrf, device, *destinations):
    for dest in destinations:
        Route.objects.create(vrf=vrf, device=device, destination=dest, protocol="static")


@pytest.mark.django_db
def test_raw_collect_writes_routes_with_device(client, device):
    """修好之后：每条路由都带上 device（原先漏传 → 一条都写不进去）"""
    resp = client.post(RAW_URL, {"device_id": device.pk, "raw_text": RAW_TEXT, "vrf_name": "default"}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 3
    routes = Route.objects.filter(vrf__device=device)
    assert routes.count() == 3
    assert set(routes.values_list("destination", flat=True)) == {"10.1.1.0/24", "10.2.0.0/16", "10.3.0.0/16"}
    assert all(route.device_id == device.pk for route in routes)


@pytest.mark.django_db
def test_raw_collect_replaces_existing_routes(client, device):
    """采集是「整表替换」：旧路由删掉，新路由写进来"""
    vrf = Vrf.objects.create(device=device, name="default")
    _seed(vrf, device, "192.0.2.0/24", "198.51.100.0/24")

    resp = client.post(RAW_URL, {"device_id": device.pk, "raw_text": RAW_TEXT, "vrf_name": "default"}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {
        "success": True,
        "device": device.hostname,
        "vrf": "default",
        "deleted": 2,
        "created": 3,
    }
    assert not Route.objects.filter(destination="192.0.2.0/24").exists()


@pytest.mark.django_db
def test_raw_collect_dedupes_within_one_batch(client, device):
    """同一 (destination, nexthop) 重复出现要去重：Route 上有 uni_route_vrf_dst_nh"""
    twice = "S    10.2.0.0/16 [1/0] via 10.1.1.254\n" * 2

    resp = client.post(RAW_URL, {"device_id": device.pk, "raw_text": twice, "vrf_name": "default"}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 1
    assert Route.objects.filter(vrf__device=device).count() == 1


@pytest.mark.django_db
def test_raw_collect_keeps_old_routes_when_save_fails(client, device):
    """保存失败必须整体回滚：不能出现「旧路由已删、新路由没进」"""
    vrf = Vrf.objects.create(device=device, name="default")
    _seed(vrf, device, "192.0.2.0/24")

    # destination 超过 45 字符 → bulk_create 时数据库直接报错
    too_long = "S    " + "10.0.0.0/24" + "A" * 60 + " via 10.1.1.254\n"
    resp = client.post(RAW_URL, {"device_id": device.pk, "raw_text": too_long, "vrf_name": "default"}, format="json")

    assert resp.status_code == 500
    assert Route.objects.filter(vrf=vrf).count() == 1, "失败的采集把原有路由删掉了"
    assert Route.objects.filter(destination="192.0.2.0/24").exists()


@pytest.mark.django_db
def test_collect_saves_parsed_routes(client, device, monkeypatch):
    """route_collect：外部接口取文本 + TTP 解析 → 保存（TTP 用假 parser，见模块 docstring）"""

    class _Resp:
        text = "任意文本"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("ops.api.trace.requests.get", lambda *args, **kwargs: _Resp())

    class _FakeTTP:
        def __init__(self, *args, **kwargs):
            pass

        def parse(self):
            return None

        def result(self, format=None):
            return [{"routes": [{"destination": "10.9.0.0/16", "nexthop": "10.1.1.254", "protocol": "static"}]}]

    monkeypatch.setattr("ttp.ttp", _FakeTTP)

    resp = client.post(
        API_URL,
        {"device_id": device.pk, "api_url": "http://example.invalid/routes", "template": "route"},
        format="json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["created"] == 1
    route = Route.objects.get(vrf__device=device)
    assert route.destination == "10.9.0.0/16"
    assert route.device_id == device.pk
