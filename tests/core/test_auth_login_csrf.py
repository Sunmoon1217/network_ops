"""`/api/auth/login/` 不能被 CSRF 拦住。

起因（实测）：浏览器里登录过 `/admin/` 之后，`/api/auth/login/` 会 403，而同一个地址换成
`127.0.0.1` 就能登录。差别不在 nginx，而在 **cookie 的作用域**：

- `localhost:8000` → 浏览器带上 `localhost` 的 `sessionid`
- `127.0.0.1:8000` → cookie 主机不匹配，带不上

`REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` 里有 `SessionAuthentication`，而 DRF 的
`SessionAuthentication.authenticate()` 在「请求带着**已认证**的 session」时会调用
`enforce_csrf(request)`——这条路径是 DRF 自己发起的，**绕开**中间件层面的 `csrf_exempt`
（DRF 的 `APIView.as_view()` 本来就对整个视图 `csrf_exempt`）。前端的 axios 不带 CSRF token，
于是 403；不带 session 时 `SessionAuthentication` 直接返回 None，CSRF 校验根本不发生。

而 `/api/auth/login/` 是「用账号密码换 token」的接口：它不需要任何身份，也就没有任何
需要 CSRF 保护的东西（真正的危险是「已登录用户被第三方页面借用身份」，这里不存在）。
所以它应当显式关掉认证，而不是依赖调用方别带 cookie。
"""

import pytest
from django.test import Client

from core.models import User

LOGIN_URL = "/api/auth/login/"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="_t_login_csrf", password="pw-abc-123")


@pytest.mark.django_db
def test_login_works_without_session_cookie(user):
    """对照：没带 cookie 时本来就正常（这也解释了 127.0.0.1 为什么能用）。"""
    client = Client(enforce_csrf_checks=True)

    resp = client.post(
        LOGIN_URL,
        {"username": user.username, "password": "pw-abc-123"},
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["token"]


@pytest.mark.django_db
def test_token_authenticated_request_is_unaffected_by_session_cookie(user):
    """对照：带 `Authorization: Token ...` 的请求不受 session cookie 影响。

    `_authenticate()` 按 `DEFAULT_AUTHENTICATION_CLASSES` 顺序试，TokenAuthentication
    先命中就返回了，`SessionAuthentication` 根本不会执行——所以**只有**不带 token 的
    `login` 会踩到这个坑（`logout` / `me` 前端都会带上 token）。
    """
    from rest_framework.authtoken.models import Token as DRFToken

    token = DRFToken.objects.create(user=user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)  # 同时带着 session cookie

    resp = client.get("/api/me/", HTTP_AUTHORIZATION=f"Token {token.key}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["username"] == user.username


@pytest.mark.django_db
def test_login_not_blocked_by_csrf_when_browser_has_session(user):
    """浏览器带着 sessionid（登录过 /admin/）时，登录接口必须照常可用。

    `HTTP_ORIGIN` / `HTTP_HOST` 都设成**互相一致**的值：这样即使 CSRF 校验真的发生，
    失败原因也不会是 Origin（因此这条测试只可能因为 CSRF token 而失败）。
    """
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)  # 只写 session cookie，不带 Authorization 头

    resp = client.post(
        LOGIN_URL,
        {"username": user.username, "password": "pw-abc-123"},
        content_type="application/json",
        HTTP_HOST="localhost:8000",
        HTTP_ORIGIN="http://localhost:8000",
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["token"]
