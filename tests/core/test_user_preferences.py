"""`/api/me/preferences/`：按用户保存的前端配置（表格列宽等）。

守住的边界：

- 偏好**按用户隔离**——两个用户同 key 互不可见（这是「每个用户的前端配置」的题眼）；
- PUT 是**单条 upsert** 而不是全量替换，两张表各自回写不会互相覆盖；
- value 传 null 即删除该条（用 null 表达「清除」，省一个专门语义）；
- key 缺失 / 超长 / value 缺失都 400，不进数据库；
- 未认证一律 401（全局 IsAuthenticated，但这是新接口，显式钉住）。
"""

import pytest
from rest_framework.test import APIClient

from core.models import User, UserPreference

PREFS_URL = "/api/me/preferences/"


def authed_client(username="prefuser"):
    user = User.objects.create_user(username=username, password="pw-prefuser-9x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_requires_authentication():
    resp = APIClient().get(PREFS_URL)

    assert resp.status_code == 401


@pytest.mark.django_db
def test_get_returns_empty_dict_for_new_user():
    client, _ = authed_client()

    resp = client.get(PREFS_URL)

    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.django_db
def test_put_upserts_single_key_and_get_returns_all():
    client, _ = authed_client()

    resp = client.put(
        PREFS_URL,
        {"key": "table:devices.interfaces:column-widths", "value": {"ip": 180}},
        content_type="application/json",
    )
    assert resp.status_code == 200

    # 同 key 再写是覆盖（upsert），不是追加第二行
    client.put(
        PREFS_URL,
        {"key": "table:devices.interfaces:column-widths", "value": {"ip": 220}},
        content_type="application/json",
    )
    client.put(
        PREFS_URL,
        {"key": "table:devices.accounts:column-widths", "value": {"username": 140}},
        content_type="application/json",
    )

    body = client.get(PREFS_URL).json()
    assert body == {
        "table:devices.interfaces:column-widths": {"ip": 220},
        "table:devices.accounts:column-widths": {"username": 140},
    }
    # 每个 (user, key) 只有一行
    assert UserPreference.objects.filter(key="table:devices.interfaces:column-widths").count() == 1


@pytest.mark.django_db
def test_put_is_partial_not_full_replace():
    """单条 upsert：写第二张表的列宽不会冲掉第一张表的。"""
    client, _ = authed_client()
    client.put(PREFS_URL, {"key": "table:a:column-widths", "value": {"x": 100}}, content_type="application/json")

    client.put(PREFS_URL, {"key": "table:b:column-widths", "value": {"y": 200}}, content_type="application/json")

    body = client.get(PREFS_URL).json()
    assert "table:a:column-widths" in body and "table:b:column-widths" in body


@pytest.mark.django_db
def test_preferences_are_isolated_per_user():
    """题眼：同一 key，两个用户各存各的，互不可见。"""
    client_a, user_a = authed_client("alice")
    client_b, user_b = authed_client("bob")

    client_a.put(
        PREFS_URL,
        {"key": "table:devices.list:column-widths", "value": {"hostname": 300}},
        content_type="application/json",
    )
    client_b.put(
        PREFS_URL,
        {"key": "table:devices.list:column-widths", "value": {"hostname": 120}},
        content_type="application/json",
    )

    assert client_a.get(PREFS_URL).json() == {"table:devices.list:column-widths": {"hostname": 300}}
    assert client_b.get(PREFS_URL).json() == {"table:devices.list:column-widths": {"hostname": 120}}
    assert UserPreference.objects.filter(user=user_a).count() == 1
    assert UserPreference.objects.filter(user=user_b).count() == 1


@pytest.mark.django_db
def test_get_single_key_by_query_param():
    client, _ = authed_client()
    client.put(PREFS_URL, {"key": "table:a", "value": {"x": 1}}, content_type="application/json")
    client.put(PREFS_URL, {"key": "table:b", "value": {"y": 2}}, content_type="application/json")

    assert client.get(f"{PREFS_URL}?key=table:a").json() == {"table:a": {"x": 1}}


@pytest.mark.django_db
def test_null_value_deletes_key():
    client, _ = authed_client()
    client.put(PREFS_URL, {"key": "table:a", "value": {"x": 1}}, content_type="application/json")

    resp = client.put(PREFS_URL, {"key": "table:a", "value": None}, content_type="application/json")

    assert resp.status_code == 200
    assert resp.json() == {"key": "table:a", "value": None}
    assert client.get(PREFS_URL).json() == {}


@pytest.mark.django_db
def test_delete_by_key():
    client, _ = authed_client()
    client.put(PREFS_URL, {"key": "table:a", "value": {"x": 1}}, content_type="application/json")

    resp = client.delete(f"{PREFS_URL}?key=table:a")

    assert resp.status_code == 200
    assert client.get(PREFS_URL).json() == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {},  # key / value 都缺
        {"value": {"x": 1}},  # 缺 key
        {"key": "", "value": {"x": 1}},  # 空 key
        {"key": "k" * 101, "value": {}},  # 超过模型 max_length=100
        {"key": "table:a"},  # 缺 value
    ],
)
def test_bad_payloads_return_400(payload):
    client, _ = authed_client()

    resp = client.put(PREFS_URL, payload, content_type="application/json")

    assert resp.status_code == 400
    assert UserPreference.objects.count() == 0
