"""``/api/access-flows/``：只读查询、鉴权、设备/策略过滤。"""

import pytest
from rest_framework.authtoken.models import Token as DRFToken
from rest_framework.test import APIClient

from analysis.models import AccessFlow
from analysis.policy_expand import upsert_flows
from assets.models import Device
from core.models import User

URL = "/api/access-flows/"


def _unauthenticated_client() -> APIClient:
    return APIClient()


@pytest.fixture
def client(db):
    user = User.objects.create_user(username="_t_af_api", password="pw-af-api-1")
    token = DRFToken.objects.create(user=user)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api


def _device(hostname: str) -> Device:
    return Device.objects.create(hostname=hostname, device_type="firewall")


def _seed(device: Device, policy_pk: int, *, src_ip: str = "10.0.0.1", port: str = "80") -> AccessFlow:
    context = {
        "device_id": device.pk,
        "hostname": device.hostname,
        "policy_pk": policy_pk,
        "policy_id": str(policy_pk),
        "name": f"p-{policy_pk}",
        "action": "allow",
        "order": 0,
        "enabled": True,
    }
    key = (src_ip, 32, "", "10.0.0.2", 32, "", "tcp", port, "", "allow")
    upsert_flows([{"key": key, "contexts": {f"{device.pk}:{policy_pk}": context}}])
    return AccessFlow.objects.get(src_ip=src_ip, port=port)


def test_requires_authentication(db):
    assert _unauthenticated_client().get(URL).status_code in (401, 403)


@pytest.mark.django_db
def test_list_returns_paginated_flows_with_key_fields(client):
    device = _device("_t_afapi_list")
    _seed(device, 1)

    resp = client.get(URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["src_ip"] == "10.0.0.1"
    assert row["src_prefix"] == 32
    assert row["protocol"] == "tcp"
    assert row["port"] == "80"
    assert row["action"] == "allow", "action 进唯一键后必须出现在 API 返回里"
    assert row["device_ids"] == [device.pk]
    assert list(row["contexts"]) == [f"{device.pk}:1"], "contexts 键形如 <device_pk>:<policy_pk>"


@pytest.mark.django_db
def test_device_filter_uses_gin_containment(client):
    device_a, device_b = _device("_t_afapi_a"), _device("_t_afapi_b")
    _seed(device_a, 1)
    _seed(device_b, 1, src_ip="192.0.2.1", port="22")

    resp = client.get(URL, {"device": device_a.pk})

    body = resp.json()
    assert body["count"] == 1
    assert body["results"][0]["src_ip"] == "10.0.0.1"


@pytest.mark.django_db
def test_policy_filter(client):
    device = _device("_t_afapi_pol")
    _seed(device, 11)
    _seed(device, 22, src_ip="192.0.2.5", port="443")

    row = AccessFlow.objects.get(device_ids__contains=[device.pk], contexts__has_key=f"{device.pk}:11")
    resp = client.get(URL, {"policy": row.policy_ids[0]})

    body = resp.json()
    assert body["count"] == 1
    assert body["results"][0]["port"] == "80"


@pytest.mark.django_db
def test_invalid_filter_param_is_400(client):
    resp = client.get(URL, {"device": "not-a-number"})
    assert resp.status_code == 400
    assert "device" in resp.json()


@pytest.mark.django_db
def test_action_filter(client):
    """?action=allow|deny 行级过滤（action 进唯一键后面板的允许/拒绝筛选）"""
    device = _device("_t_afapi_action")
    _seed(device, 1)  # key 带 allow → 行 action=allow
    deny_row = _seed(device, 2, src_ip="192.0.2.9", port="53")
    AccessFlow.objects.filter(pk=deny_row.pk).update(action="deny")

    body = client.get(URL, {"action": "deny"}).json()
    assert body["count"] == 1
    assert body["results"][0]["action"] == "deny"

    body = client.get(URL, {"action": "allow"}).json()
    assert body["count"] == 1
    assert body["results"][0]["action"] == "allow"

    resp = client.get(URL, {"action": "yes"})
    assert resp.status_code == 400
    assert "action" in resp.json()


@pytest.mark.django_db
def test_search_matches_ip_and_port(client):
    device = _device("_t_afapi_search")
    _seed(device, 1, src_ip="10.9.8.7", port="8080")

    resp = client.get(URL, {"search": "10.9.8.7"})
    assert resp.json()["count"] == 1

    resp = client.get(URL, {"search": "10.0.0.1"})
    assert resp.json()["count"] == 0
