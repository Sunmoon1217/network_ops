"""``core.integrations``：provider 注册表与外部 client 的生命周期。

迁移前 Zabbix 的单例住在 ``apps/ingest/collectors/zabbix/``，而 ``close_zapi()`` 在全项目
**没有调用点**——session 一直泄漏到进程退出。现在实例归 core 统管：业务域只注册 provider，
core 只负责「按 (system, instance) 取实例」与「释放全部」。

这里锁住四件事：

1. 取实例一律走 provider，core 不缓存第二份（两份状态 = 「以为释放了其实没有」）；
2. 未注册的集成立刻报错，不返回空值、不静默降级；
3. ``release_all`` 对单个 provider 失败隔离，且可以被重复调用（进程收尾可能触发多次）；
4. ingest 侧的 ``get_zapi`` 只是兼容转发，符号必须与 core 的同一份实现。
"""

import asyncio

import pytest

from core.integrations import (
    acquire,
    acquire_sync,
    describe_all,
    get_provider,
    register_provider,
    registered,
    release_all,
)


class _FakeProvider:
    """最小 provider：只记调用次数，不碰任何真实外部系统。"""

    system = "fake"
    instance = "default"

    def __init__(self, *, release_error: Exception | None = None) -> None:
        self.acquired = 0
        self.released = 0
        self._release_error = release_error

    async def acquire(self) -> dict[str, str]:
        self.acquired += 1
        return {"client": "fake"}

    async def release(self) -> None:
        self.released += 1
        if self._release_error is not None:
            raise self._release_error

    def describe(self) -> dict[str, object]:
        return {"system": self.system, "instance": self.instance, "configured": False}


@pytest.fixture
def registry(monkeypatch):
    """每个用例一份注册表快照：注册 / 覆盖不泄漏到其它用例。"""
    from core.integrations import registry as registry_module

    monkeypatch.setattr(registry_module, "_providers", dict(registry_module._providers))
    return registry_module


def test_acquire_goes_through_provider(registry):
    provider = _FakeProvider()
    register_provider(provider)

    assert asyncio.run(acquire("fake")) == {"client": "fake"}
    assert provider.acquired == 1
    assert get_provider("fake") is provider


def test_register_last_wins_and_stays_single(registry):
    first, second = _FakeProvider(), _FakeProvider()
    register_provider(first)
    register_provider(second)

    assert get_provider("fake") is second
    assert registry.registered().count(("fake", "default")) == 1


def test_unknown_integration_raises(registry):
    """未注册不返回 None：宁可启动期/调用期立刻炸，也不要「拿不到 client 就走空数据」。"""
    with pytest.raises(LookupError, match="未注册的集成"):
        get_provider("no-such-system")


def test_release_all_isolates_failures(registry):
    broken = _FakeProvider(release_error=RuntimeError("boom"))
    healthy = _FakeProvider()
    healthy.system = "fake-ok"
    register_provider(broken)
    register_provider(healthy)

    asyncio.run(release_all())  # 不向外抛

    assert broken.released == 1
    assert healthy.released == 1


def test_release_all_can_run_twice(registry):
    """进程收尾可能重复触发（ASGI shutdown + Celery 信号）：core 只保证调用到 provider，
    「重复调用安全」是 provider 自己的契约（Zabbix 的 close_zapi 就是幂等的）。"""
    provider = _FakeProvider()
    register_provider(provider)

    asyncio.run(release_all())
    asyncio.run(release_all())

    assert provider.released == 2


def test_acquire_sync_rejects_async_only_provider(registry):
    """绝不在同步栈里偷偷 asyncio.run：async-only 的 provider 直接报错。"""
    register_provider(_FakeProvider())

    with pytest.raises(TypeError, match="只提供异步"):
        acquire_sync("fake")


def test_zabbix_provider_registered_by_ingest(registry):
    """ingest 在 ready() 里注册 Zabbix —— Django 起来后注册表里就该有它。"""
    assert ("zabbix", "default") in registered()
    described = next(item for item in describe_all() if item["system"] == "zabbix")
    assert described["instance"] == "default"
    assert "configured" in described


def test_ingest_forwarder_is_the_core_client():
    """``ingest.collectors.zabbix.get_zapi`` 必须就是 core 那一份（兼容层不许复制逻辑）。"""
    from core.integrations.providers.zabbix import get_zapi as core_get_zapi
    from ingest.collectors.zabbix import get_zapi as ingest_get_zapi

    assert ingest_get_zapi is core_get_zapi


def test_asgi_lifespan_hook_releases_on_shutdown(registry):
    """ASGI 收尾钩子真的会调 release_all（不是只有一份清单摆着好看）。"""
    from netops.asgi import _release_integrations

    provider = _FakeProvider()
    register_provider(provider)

    async def _enter_and_exit():
        async with _release_integrations():
            pass

    asyncio.run(_enter_and_exit())

    assert provider.released == 1


def test_celery_shutdown_hook_releases(registry):
    """Celery 子进程退出同样走到 release_all（直接调处理函数，不启 worker）。"""
    from netops.celery import _release_integrations as release_on_worker_shutdown

    provider = _FakeProvider()
    register_provider(provider)

    release_on_worker_shutdown()

    assert provider.released == 1
