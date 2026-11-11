"""MCP 出口接入层（``netops/mcp_gateway.py``）：路径判定、IP 取值、匿名限流、关闭时的 404。

限流用例全都用**假 Redis**（不连真实例）：要断言的是「超限之后回什么」「Redis 挂了怎么办」，
真去 INCR 会把单测绑到运行环境上，还会留下串味的计数键。

另一条守的是开关的**表现**而不是实现：``MCP_ENABLED=0`` 时 ``/mcp`` 必须自己回 404，绝不能
落到 Django 的 SPA 兜底——那里会返回 200 + ``index.html``，客户端看到的是「JSON 解析失败」，
与「nginx 少配 location」是同一个坑。
"""

import asyncio
import json

import pytest
import redis as redis_module
from django.test import override_settings

from netops import asgi, mcp_gateway


class _FakeRedis:
    """只实现 ``_over_limit`` 用得到的三样：上下文管理、incr、expire。"""

    def __init__(self, *, fail: bool = False):
        self.counts: dict[str, int] = {}
        self.expires: list[tuple[str, int]] = []
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def incr(self, key: str) -> int:
        if self.fail:
            raise redis_module.RedisError("connection refused")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, ttl: int) -> None:
        self.expires.append((key, ttl))


def _patch_redis(monkeypatch, fake: _FakeRedis) -> _FakeRedis:
    monkeypatch.setattr(mcp_gateway.redis, "from_url", lambda *args, **kwargs: fake)
    return fake


def _scope(path: str = "/mcp", *, headers=(), client=("10.0.0.1", 4321)) -> dict:
    return {"type": "http", "path": path, "headers": list(headers), "client": client}


def _run(coro):
    return asyncio.run(coro)


def _drive(app, scope) -> list[dict]:
    """跑一遍 app，收集它发出的 ASGI 消息。"""

    async def receive():
        return {"type": "http.request"}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    _run(app(scope, receive, send))
    return sent


def _body(sent: list[dict]) -> dict:
    return json.loads(sent[-1]["body"])


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/mcp", True), ("/mcp/", True), ("/mcp/messages", True), ("/mcpx", False), ("/api/mcp", False), ("/", False)],
)
def test_is_mcp_path(path, expected):
    assert mcp_gateway.is_mcp_path(path) is expected


@pytest.mark.parametrize(
    ("headers", "client", "expected"),
    [
        # nginx 用 $remote_addr 覆盖 X-Real-IP，客户端伪造不了 → 它优先
        ([(b"x-real-ip", b"203.0.113.9"), (b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")], ("10.0.0.1", 1), "203.0.113.9"),
        # 没有 X-Real-IP 时取 XFF 首跳（$proxy_add_x_forwarded_for 会保留客户端自带的那个）
        ([(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")], ("10.0.0.1", 1), "1.1.1.1"),
        # 都没有就退回 ASGI client（直连 uvicorn / 测试客户端）
        ([], ("10.0.0.1", 1), "10.0.0.1"),
        # 连 client 都没有：所有这种请求共用一个桶，而不是崩掉
        ([], None, "unknown"),
    ],
)
def test_client_ip(headers, client, expected):
    assert mcp_gateway.client_ip(_scope(headers=headers, client=client)) == expected


@override_settings(MCP_RATE_LIMIT_PER_MINUTE=2)
def test_quota_allows_then_429(monkeypatch):
    fake = _patch_redis(monkeypatch, _FakeRedis())
    handled: list[dict] = []

    async def app(scope, receive, send):
        handled.append(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})

    scope = _scope()
    for _ in range(2):
        assert _drive(mcp_gateway.McpGuardMiddleware(app), scope)[0]["status"] == 200

    sent = _drive(mcp_gateway.McpGuardMiddleware(app), scope)
    assert sent[0]["status"] == 429
    assert "频率超限" in _body(sent)["detail"]
    assert len(handled) == 2  # 超限那次没有进 MCP 子应用
    # 窗口键只会在第一次计数时设过期，TTL 覆盖两个窗口
    assert list(fake.counts.values()) == [3]
    assert all(ttl == 120 for _, ttl in fake.expires)


@override_settings(MCP_RATE_LIMIT_PER_MINUTE=0)
def test_zero_means_no_limit(monkeypatch):
    fake = _patch_redis(monkeypatch, _FakeRedis())

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    for _ in range(5):
        assert _drive(mcp_gateway.McpGuardMiddleware(app), _scope())[0]["status"] == 200

    assert fake.counts == {}  # 0 = 不计数，连 Redis 都不碰


@override_settings(MCP_RATE_LIMIT_PER_MINUTE=1)
def test_redis_failure_fails_open(monkeypatch, caplog):
    """Redis 不可用时放行并留一行告警：护栏不该把出口搞挂。"""
    _patch_redis(monkeypatch, _FakeRedis(fail=True))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent = _drive(mcp_gateway.McpGuardMiddleware(app), _scope())

    assert sent[0]["status"] == 200
    assert any("限流计数失败" in record.message for record in caplog.records)


def test_non_mcp_paths_are_not_guarded(monkeypatch):
    """限流只挂在 /mcp 上：/api 那条热路径不该多一次 Redis 往返。"""
    fake = _patch_redis(monkeypatch, _FakeRedis())
    seen: list[str] = []

    async def app(scope, receive, send):
        seen.append(scope["path"])

    _drive(mcp_gateway.McpGuardMiddleware(app), _scope("/api/devices/"))

    assert seen == ["/api/devices/"]
    assert fake.counts == {}


def test_dispatch_returns_explicit_404_when_disabled(monkeypatch):
    """关闭时 /mcp 必须自己回 404，不能交给 Django（SPA 兜底会返回 200 + index.html）。"""
    monkeypatch.setattr(asgi, "mcp_http_app", None)
    django_calls: list[str] = []

    async def django_app(scope, receive, send):
        django_calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})

    monkeypatch.setattr(asgi, "django_application", django_app)

    sent = _drive(asgi._dispatch, _scope("/mcp"))

    assert sent[0]["status"] == 404
    assert "MCP_ENABLED" in _body(sent)["detail"]
    assert django_calls == []

    # 其余路径照旧交给 Django
    _drive(asgi._dispatch, _scope("/api/devices/"))
    assert django_calls == ["/api/devices/"]


def test_dispatch_hands_mcp_paths_to_the_guarded_app(monkeypatch):
    monkeypatch.setattr(asgi, "mcp_http_app", mcp_gateway.McpGuardMiddleware(_recorder(seen := [])))

    _drive(asgi._dispatch, _scope("/mcp"))

    assert seen == ["/mcp"]


def _recorder(seen: list[str]):
    async def app(scope, receive, send):
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})

    return app
