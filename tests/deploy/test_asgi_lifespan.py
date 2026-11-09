"""ASGI lifespan 契约（部署层）。

守的是这条实测链路：Django 6.1 的 ASGIHandler 收到 lifespan scope 直接抛 ValueError，
uvicorn 的 ``lifespan=auto`` 遇到异常只记一行 info「ASGI 'lifespan' protocol appears
unsupported.」然后照常服务。所以 ``netops/asgi.py`` 必须把 Django handler 包进
``LifespanApp``：完成握手、跑启动/关闭钩子，并且钩子失败要回 ``*.failed`` 消息
（直接抛异常会被 uvicorn 当成「app 不支持 lifespan」，静默降级、worker 照常起来）。
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest

from netops.lifespan import LifespanApp


def _run(coro):
    return asyncio.run(coro)


async def _noop_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})


async def _handshake(app, *, events=("startup", "shutdown"), state=None):
    """模拟 uvicorn LifespanOn：往队列投消息，收集 app 的应答。"""
    queue = asyncio.Queue()
    for event in events:
        queue.put_nowait({"type": f"lifespan.{event}"})
    sent = []

    async def receive():
        return await queue.get()

    async def send(message):
        sent.append(message)

    scope = {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}}
    if state is not None:
        scope["state"] = state
    await app(scope, receive, send)
    return sent


def test_handshake_runs_hooks_in_order_and_shares_state():
    events = []

    @asynccontextmanager
    async def hook(name):
        events.append(f"enter:{name}")
        try:
            yield
        finally:
            events.append(f"exit:{name}")

    app = LifespanApp(_noop_app, [lambda: hook("a"), lambda: hook("b")])
    server_state = {}
    sent = _run(_handshake(app, state=server_state))

    assert [m["type"] for m in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert events == ["enter:a", "enter:b", "exit:b", "exit:a"]  # AsyncExitStack 逆序退出
    assert app.state is server_state  # 沿用 uvicorn 的 state dict，钩子放的资源请求侧可见


def test_http_scope_is_forwarded_unchanged_with_state():
    seen = []

    async def downstream(scope, receive, send):
        seen.append((scope, receive, send))

    app = LifespanApp(downstream)
    state = {"pool": object()}
    _run(_handshake(app, state=state))

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        pass

    http_scope = {"type": "http", "path": "/api/"}
    _run(app(http_scope, receive, send))

    scope, got_receive, got_send = seen[0]
    assert (scope["type"], scope["path"]) == ("http", "/api/")
    assert scope["state"] is state
    assert got_receive is receive and got_send is send  # 原样透传，不做二次包装
    assert "state" not in http_scope  # 服务器可能复用 scope，不能就地改


def test_startup_failure_reports_failed_and_rolls_back(caplog):
    events = []

    @asynccontextmanager
    async def ok():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    @asynccontextmanager
    async def broken():
        raise RuntimeError("boom")
        yield  # noqa: F704 — 只为让它成为异步生成器，永不可达

    app = LifespanApp(_noop_app, [ok, broken])
    with caplog.at_level(logging.ERROR, logger="netops.lifespan"):
        sent = _run(_handshake(app))

    assert sent[0]["type"] == "lifespan.startup.failed"  # 让 uvicorn 退出 worker，而不是静默降级
    assert "RuntimeError: boom" in sent[0]["message"]
    assert sent[1]["type"] == "lifespan.shutdown.complete"
    assert events == ["enter", "exit"]  # 已进入的钩子被回滚
    assert any("startup 失败" in r.message for r in caplog.records)


def test_shutdown_failure_reports_failed(caplog):
    @asynccontextmanager
    async def bad_exit():
        yield
        raise RuntimeError("close boom")

    app = LifespanApp(_noop_app, [bad_exit])
    with caplog.at_level(logging.ERROR, logger="netops.lifespan"):
        sent = _run(_handshake(app))

    assert sent[0]["type"] == "lifespan.startup.complete"
    assert sent[1]["type"] == "lifespan.shutdown.failed"
    assert "close boom" in sent[1]["message"]


def test_duplicate_startup_does_not_reenter_hooks():
    calls = []

    @asynccontextmanager
    async def hook():
        calls.append("enter")
        yield

    app = LifespanApp(_noop_app, [hook])
    sent = _run(_handshake(app, events=("startup", "startup", "shutdown")))

    assert [m["type"] for m in sent] == [
        "lifespan.startup.complete",
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]
    assert calls == ["enter"]  # session_manager.run() 这类钩子只允许进一次


def test_missing_lifespan_warns_once(caplog):
    """换 sync/gthread worker 或 uvicorn --lifespan off 时，钩子会静默不跑——不许无声无息。"""
    app = LifespanApp(_noop_app)

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        pass

    with caplog.at_level(logging.WARNING, logger="netops.lifespan"):
        for _ in range(2):
            _run(app({"type": "http", "path": "/"}, receive, send))

    warnings = [r for r in caplog.records if r.name == "netops.lifespan"]
    assert len(warnings) == 1
    assert "worker-class" in warnings[0].message


def test_asgi_application_wires_lifespan_over_django():
    from django.core.handlers.asgi import ASGIHandler

    from netops.asgi import LIFESPAN_HOOKS, application, django_application

    assert isinstance(application, LifespanApp)
    assert isinstance(django_application, ASGIHandler)
    assert application.app is django_application
    assert LIFESPAN_HOOKS == []  # 钩子清单只在 asgi.py 组合，基建不自己注册

    sent = _run(_handshake(application))
    assert [m["type"] for m in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_django_handler_rejects_lifespan():
    """为什么非要包这一层：这条红了说明 Django 恢复了 lifespan 支持，需重新评估包装层。"""
    from netops.asgi import django_application

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        pass

    with pytest.raises(ValueError, match="lifespan"):
        _run(django_application({"type": "lifespan"}, receive, send))
