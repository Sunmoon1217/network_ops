"""用户权限契约测试（core.permissions.IsOperatorOrReadOnly）。

矩阵：

- 匿名：一律 401（连读都不行）
- 普通用户（role=normal）：读 200，写 403
- 操作员（role=operator）：读 200，写 201/200
- 超管：恒放行（is_superuser 不看 role）
- login / register 保持公开（匿名可用）
- /api/me/ 返回 role，注册出来的账号 role=normal
"""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from assets.models import Device
from core.models import User

DEVICES_URL = "/api/assets/devices/"


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_anonymous_cannot_even_read():
    """匿名连查询都不行（普通用户才对应查询权限）"""
    assert APIClient().get(DEVICES_URL).status_code == 401


@pytest.mark.django_db
def test_normal_user_can_read(normal_user):
    """普通用户：查询放行"""
    Device.objects.create(hostname="perm-read-dev", device_type="switch")

    resp = _auth_client(normal_user).get(DEVICES_URL)

    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.django_db
def test_normal_user_cannot_write(normal_user):
    """普通用户：增删改一律 403"""
    client = _auth_client(normal_user)
    device = Device.objects.create(hostname="perm-write-dev", device_type="switch")

    assert client.post(DEVICES_URL, {"hostname": "x", "device_type": "switch"}, format="json").status_code == 403
    assert client.patch(f"{DEVICES_URL}{device.pk}/", {"remark": "x"}, format="json").status_code == 403
    assert client.put(
        f"{DEVICES_URL}{device.pk}/", {"hostname": "x", "device_type": "switch"}, format="json"
    ).status_code == 403
    assert client.delete(f"{DEVICES_URL}{device.pk}/").status_code == 403
    # 被拒的写没有落库
    assert not Device.objects.filter(hostname="x").exists()


@pytest.mark.django_db
def test_operator_can_write(operator_user):
    """操作员：增删改放行"""
    client = _auth_client(operator_user)

    created = client.post(DEVICES_URL, {"hostname": "perm-op-dev", "device_type": "switch"}, format="json")
    assert created.status_code == 201, created.content

    patched = client.patch(f"{DEVICES_URL}{created.json()['id']}/", {"remark": "改过"}, format="json")
    assert patched.status_code == 200

    assert client.delete(f"{DEVICES_URL}{created.json()['id']}/").status_code == 204


@pytest.mark.django_db
def test_superuser_always_allowed_to_write():
    """超管不看 role，恒可写（ensure_superuser 建的 admin 不需要另配 role）"""
    admin = User.objects.create_superuser(username="_t_perm_admin", password="x")

    resp = _auth_client(admin).post(DEVICES_URL, {"hostname": "perm-admin-dev", "device_type": "switch"}, format="json")

    assert resp.status_code == 201


@pytest.mark.django_db
def test_login_and_register_stay_public():
    """登录 / 注册是公开接口：匿名可用（不受全局权限影响）"""
    User.objects.create_user(username="perm-login-user", password="x")

    login = APIClient().post("/api/auth/login/", {"username": "perm-login-user", "password": "x"})
    assert login.status_code == 200
    assert "token" in login.json()

    register = APIClient().post(
        "/api/auth/register/",
        {"username": "perm-new-user", "password": "x-perm-12345"},
    )
    assert register.status_code == 201, register.content


@pytest.mark.django_db
def test_register_creates_normal_role_user():
    """注册出来的账号是普通用户（role=normal），拿 token 也只能读"""
    register = APIClient().post(
        "/api/auth/register/",
        {"username": "perm-role-user", "password": "x-perm-12345"},
    )
    assert register.status_code == 201

    user = User.objects.get(username="perm-role-user")
    assert user.role == "normal"
    assert not user.is_operator

    token = Token.objects.get(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.get(DEVICES_URL).status_code == 200
    assert client.post(DEVICES_URL, {"hostname": "x", "device_type": "switch"}, format="json").status_code == 403


@pytest.mark.django_db
def test_me_endpoint_returns_role_and_can_write(normal_user, operator_user):
    """前端靠 /api/me/ 的 role / can_write 决定是否展示写入口"""
    reader = _auth_client(normal_user).get("/api/me/").json()
    assert reader["role"] == "normal"
    assert reader["can_write"] is False

    writer = _auth_client(operator_user).get("/api/me/").json()
    assert writer["role"] == "operator"
    assert writer["can_write"] is True


@pytest.mark.django_db
def test_superuser_can_write_even_with_normal_role():
    """超管 role 仍是 normal（默认），但 can_write 必须为 True"""
    admin = User.objects.create_superuser(username="_t_perm_admin2", password="x")
    assert admin.role == "normal"

    payload = _auth_client(admin).get("/api/me/").json()

    assert payload["can_write"] is True


@pytest.mark.django_db
def test_self_service_endpoints_stay_authenticated(normal_user):
    """改密码 / 偏好 / 登出是自服务接口：普通用户可用，不要求操作员"""
    client = _auth_client(normal_user)

    # 偏好读写（PUT / GET）
    put = client.put("/api/me/preferences/", {"key": "table:x", "value": {"a": 1}}, format="json")
    assert put.status_code == 200
    assert client.get("/api/me/preferences/").json()["table:x"] == {"a": 1}

    # 登出（POST）
    assert client.post("/api/auth/logout/").status_code == 200


@pytest.mark.django_db
def test_overview_is_read_gated(normal_user):
    """overview 也走全局权限：匿名 401、普通用户可读"""
    assert APIClient().get("/api/assets/overview/").status_code == 401
    assert _auth_client(normal_user).get("/api/assets/overview/").status_code == 200
