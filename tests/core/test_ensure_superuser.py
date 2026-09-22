"""`manage.py ensure_superuser`：容器启动时零配置地建「初始管理员」。

守四条边界（都是产品行为，不是实现细节）：没有超管才建、建完即可登录、已存在不动、
同名普通账号**不**被静默提权。
"""

import re
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from core.models import User

CMD = "ensure_superuser"
# 从启动日志里取随机密码——它就是给运维抄下来登录用的，所以这条日志本身就是契约
PASSWORD_RE = re.compile(r"初始密码：(\S+)")


def run(**kwargs):
    out = StringIO()
    call_command(CMD, stdout=out, **kwargs)
    return out.getvalue()


def logged_password(output):
    match = PASSWORD_RE.search(output)
    assert match, f"日志里没有初始密码：{output!r}"
    return match.group(1)


@pytest.mark.django_db
def test_creates_admin_and_prints_password():
    output = run()

    user = User.objects.get(username="admin")
    assert user.is_superuser and user.is_staff and user.is_active
    assert "已创建初始管理员" in output
    # 日志里给的密码必须真的能过校验，否则运维照抄也登不进去
    assert user.check_password(logged_password(output))


@pytest.mark.django_db
def test_skips_when_superuser_already_exists():
    User.objects.create_superuser(username="someone-else", password="pw-other")

    output = run()

    assert "已存在超级用户，跳过" in output
    assert User.objects.filter(username="admin").count() == 0


@pytest.mark.django_db
def test_skips_when_admin_already_exists():
    run()
    first_password = User.objects.get(username="admin").password

    output = run()

    assert "管理员 'admin' 已存在，跳过" in output
    assert User.objects.get(username="admin").password == first_password, "已存在的账号一个字节都不该动"


@pytest.mark.django_db
def test_does_not_escalate_existing_normal_user():
    """同名账号存在但不是超管 → 只警告，绝不静默提权、也不改它的密码。"""
    User.objects.create_user(username="admin", password="pw-normal")

    output = run()

    user = User.objects.get(username="admin")
    assert not user.is_superuser and not user.is_staff
    assert user.check_password("pw-normal")
    assert "不自动提权" in output
    assert "初始密码" not in output


@pytest.mark.django_db
def test_explicit_password_is_not_echoed():
    output = run(password="pw-explicit-123")

    assert User.objects.get(username="admin").check_password("pw-explicit-123")
    assert "pw-explicit-123" not in output, "显式给的密码不该被回显"
    assert "未回显" in output


@pytest.mark.django_db
def test_update_password_resets_and_logs_new_one():
    run(password="pw-first")

    output = run(update_password=True)

    user = User.objects.get(username="admin")
    assert not user.check_password("pw-first")
    assert user.check_password(logged_password(output))


@pytest.mark.django_db
def test_custom_username_and_email():
    output = run(username="opsadmin", email="ingest@example.com")

    user = User.objects.get(username="opsadmin")
    assert user.email == "ingest@example.com"
    assert user.check_password(logged_password(output))


@pytest.mark.django_db
def test_login_works_with_logged_password():
    """建完就能用日志里那个密码登录（登录接口是 get_or_create Token，不需要预建）。"""
    password = logged_password(run())

    resp = Client().post("/api/auth/login/", {"username": "admin", "password": password})

    assert resp.status_code == 200
    assert resp.json()["token"]
