"""`POST /api/auth/register/`：注册普通账号。

守住的是**安全边界**而不是实现细节：注册出来的账号没有任何管理权限、密码过 Django 的校验器、
用户名不能大小写混淆地重复、以及「带着已登录 session 打这个接口不该被 CSRF 拦」（这条是 DRF
`SessionAuthentication` 的坑，登录接口踩过，见 `test_auth_login_csrf.py`）。
"""

import pytest
from django.test import Client

from core.models import User

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/me/"


def post(client, **payload):
    return client.post(REGISTER_URL, payload, content_type="application/json")


@pytest.mark.django_db
def test_register_creates_plain_user_and_returns_token():
    resp = post(Client(), username="wangwu", password="pw-wangwu-9x", email="w@example.com", phone="13800000000")

    assert resp.status_code == 201
    body = resp.json()
    assert body["token"]
    assert body["user"]["username"] == "wangwu"

    user = User.objects.get(username="wangwu")
    # 注册出来的必须是**普通账号**：没有任何管理权限，且处于可用状态
    assert not user.is_staff and not user.is_superuser and user.is_active
    assert user.email == "w@example.com" and user.phone == "13800000000"
    assert user.check_password("pw-wangwu-9x")


@pytest.mark.django_db
def test_token_from_register_works_immediately():
    """注册即登录：响应里的 token 能直接访问受保护接口。"""
    token = post(Client(), username="wangwu", password="pw-wangwu-9x").json()["token"]

    resp = Client().get(ME_URL, HTTP_AUTHORIZATION=f"Token {token}")

    assert resp.status_code == 200
    assert resp.json()["username"] == "wangwu"


@pytest.mark.django_db
def test_email_and_phone_are_optional():
    resp = post(Client(), username="wangwu", password="pw-wangwu-9x")

    assert resp.status_code == 201
    user = User.objects.get(username="wangwu")
    assert user.email == "" and user.phone == ""


@pytest.mark.django_db
def test_duplicate_username_rejected():
    User.objects.create_user(username="wangwu", password="pw-existing")

    resp = post(Client(), username="wangwu", password="pw-newpass-9x")

    assert resp.status_code == 400
    assert "已被占用" in str(resp.json())
    assert User.objects.filter(username="wangwu").count() == 1


@pytest.mark.django_db
def test_duplicate_username_is_rejected_case_insensitively():
    """数据库的唯一约束是大小写敏感的，只查 exact 会放过 Admin / admin 这种极易混淆的并存账号。"""
    User.objects.create_user(username="wangwu", password="pw-existing")

    resp = post(Client(), username="WangWu", password="pw-newpass-9x")

    assert resp.status_code == 400
    assert User.objects.filter(username__iexact="wangwu").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("username", "password", "why"),
    [
        ("wangwu", "12345678", "纯数字（NumericPasswordValidator）"),
        ("wangwu", "short", "太短（MinimumLengthValidator）"),
        ("wangwu", "wangwu2024", "与用户名相似（UserAttributeSimilarityValidator）"),
        ("wangwu", "password", "常见密码（CommonPasswordValidator）"),
    ],
)
def test_weak_password_rejected(username, password, why):
    resp = post(Client(), username=username, password=password)

    assert resp.status_code == 400, why
    assert "password" in resp.json(), why
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_invalid_email_rejected():
    resp = post(Client(), username="wangwu", password="pw-wangwu-9x", email="not-an-email")

    assert resp.status_code == 400
    assert "email" in resp.json()


@pytest.mark.django_db
def test_username_with_illegal_characters_rejected():
    """用户名沿用 AbstractUser 的 UnicodeUsernameValidator（空格、中文标点等都不合法）。"""
    resp = post(Client(), username="wang wu!", password="pw-wangwu-9x")

    assert resp.status_code == 400
    assert "username" in resp.json()


@pytest.mark.django_db
def test_blank_username_rejected():
    resp = post(Client(), username="   ", password="pw-wangwu-9x")

    assert resp.status_code == 400
    assert "username" in resp.json()


@pytest.mark.django_db
def test_register_is_not_blocked_by_csrf_when_session_cookie_present():
    """已登录浏览器带着 sessionid 来注册，不能被 DRF 的 SessionAuthentication 用 CSRF 拦掉。

    与 `test_auth_login_csrf.py` 同一个坑：那条路径是 DRF 自己调 enforce_csrf() 的，
    绕开中间件层面的 csrf_exempt，所以视图上必须显式 `@authentication_classes([])`。
    """
    User.objects.create_user(username="someone", password="pw-someone-9x")
    client = Client(enforce_csrf_checks=True)
    assert client.login(username="someone", password="pw-someone-9x")

    resp = post(client, username="wangwu", password="pw-wangwu-9x")

    assert resp.status_code == 201
    assert User.objects.filter(username="wangwu").exists()


@pytest.mark.django_db
def test_register_response_does_not_leak_password():
    resp = post(Client(), username="wangwu", password="pw-wangwu-9x")

    assert "password" not in resp.json()
    assert "pw-wangwu-9x" not in resp.content.decode()
