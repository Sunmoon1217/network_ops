"""`manage.py migrate_if_needed`：启动时按需迁移的判定、按后端分派的锁、以及并发串行化。

Django 自己**不**给 migrate 加锁（爬 6.1.1 源码，`advisory` 零命中），所以「检查 + 迁移」
这两步必须由本命令自己串起来才安全。这里守的是那几条容易在重构中退化的性质：
没待应用迁移时**不**执行任何迁移、有则带 `--noinput` 执行、执行期间真的持锁并按后端分派、
以及不认识的后端宁可报错也不要"静默不加锁"。
"""

import types
from contextlib import contextmanager
from io import StringIO
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections

from core.management.commands import migrate_if_needed as mod
from core.management.commands.migrate_if_needed import MIGRATION_LOCK_ID


class _FakeGraph:
    def leaf_nodes(self):
        return [("core", "0001_initial")]


class _FakeLoader:
    graph = _FakeGraph()


class _FakeExecutor:
    """只提供命令用到的那两个接口，免得为了造「有未应用迁移」去改测试库的真实状态。"""

    loader = _FakeLoader()

    def __init__(self, connection):
        self.connection = connection

    def migration_plan(self, targets):
        return [("core.0001_initial", False)]


class _FakeCursor:
    """记录 SQL 的假游标；GET_LOCK 的返回值按构造参数给。"""

    def __init__(self, log, get_lock_result):
        self.log = log
        self.get_lock_result = get_lock_result
        self._row = None

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        if "GET_LOCK" in sql:
            self._row = (self.get_lock_result,)

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeMySQLConnection:
    """假 MySQL 连接：不需要真的 MySQL，也能断言命令发出的每条 SQL。"""

    vendor = "mysql"

    def __init__(self, get_lock_result=1):
        self.log = []
        self.get_lock_result = get_lock_result

    @contextmanager
    def cursor(self):
        yield _FakeCursor(self.log, self.get_lock_result)

    @property
    def sql(self):
        return [sql for sql, _ in self.log]


@pytest.mark.django_db
def test_noop_when_up_to_date():
    """测试库的迁移全应用过 → 只打印一行跳过，不碰 call_command。"""
    out = StringIO()
    with mock.patch.object(mod, "call_command") as migrate:
        call_command("migrate_if_needed", stdout=out)
    assert not migrate.called
    assert "已是最新" in out.getvalue()


@pytest.mark.django_db
def test_runs_migrate_when_pending(monkeypatch):
    """有未应用迁移 → 调 migrate，且必须是非交互（容器里没人能回答 yes/no）。"""
    calls = []
    monkeypatch.setattr(mod, "MigrationExecutor", _FakeExecutor)
    monkeypatch.setattr(mod, "call_command", lambda name, **kwargs: calls.append((name, kwargs)))

    out = StringIO()
    call_command("migrate_if_needed", stdout=out)

    assert calls == [("migrate", {"interactive": False, "verbosity": 1})]
    assert "1 个未应用的迁移" in out.getvalue()


@pytest.mark.django_db
def test_advisory_lock_is_held_while_migrating(monkeypatch):
    """检查 + 迁移期间必须真的持有 advisory lock。

    用**另一条连接**查 `pg_locks` 而不是自证：锁是数据库层面的，本地变量糊弄不过去。
    """
    seen = []

    def fake_migrate(name, **kwargs):
        other = connections.create_connection("default")
        try:
            with other.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = %s AND objid = %s",
                    [MIGRATION_LOCK_ID >> 32, MIGRATION_LOCK_ID & 0xFFFFFFFF],
                )
                seen.append(cursor.fetchone()[0])
        finally:
            other.close()

    monkeypatch.setattr(mod, "MigrationExecutor", _FakeExecutor)
    monkeypatch.setattr(mod, "call_command", fake_migrate)

    call_command("migrate_if_needed", stdout=StringIO())

    assert seen == [1], "迁移期间没有在 pg_locks 里看到那把 advisory lock"


@pytest.mark.django_db
def test_lock_is_released_afterwards(monkeypatch):
    """跑完必须解锁：否则同一个连接上的后续启动流程会被自己挡住。"""
    monkeypatch.setattr(mod, "MigrationExecutor", _FakeExecutor)
    monkeypatch.setattr(mod, "call_command", lambda name, **kwargs: None)

    call_command("migrate_if_needed", stdout=StringIO())

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND classid = %s AND objid = %s",
            [MIGRATION_LOCK_ID >> 32, MIGRATION_LOCK_ID & 0xFFFFFFFF],
        )
        assert cursor.fetchone()[0] == 0


def test_mysql_branch_uses_get_lock(monkeypatch):
    """MySQL 后端走 GET_LOCK/RELEASE_LOCK，且用的是无限等待（-1）——不能误用 PG 的 SQL。"""
    fake = _FakeMySQLConnection()
    calls = []
    monkeypatch.setattr(mod, "connection", fake)
    monkeypatch.setattr(mod, "MigrationExecutor", _FakeExecutor)
    monkeypatch.setattr(mod, "call_command", lambda name, **kwargs: calls.append((name, kwargs)))

    call_command("migrate_if_needed", skip_checks=True, stdout=StringIO())

    assert fake.sql == ["SELECT GET_LOCK(%s, %s)", "SELECT RELEASE_LOCK(%s)"]
    assert fake.log[0][1] == [mod.MYSQL_LOCK_NAME, -1], "GET_LOCK 必须是无限等待（-1），与 PG 的阻塞语义对齐"
    assert not any("pg_advisory" in sql for sql in fake.sql)
    assert calls == [("migrate", {"interactive": False, "verbosity": 1})]


def test_mysql_lock_failure_aborts(monkeypatch):
    """GET_LOCK 返回 0（等超时）→ 报错退出，绝不在没锁的情况下迁移。"""
    fake = _FakeMySQLConnection(get_lock_result=0)
    monkeypatch.setattr(mod, "connection", fake)
    called = []
    monkeypatch.setattr(mod, "call_command", lambda *args, **kwargs: called.append(args))

    with pytest.raises(CommandError):
        call_command("migrate_if_needed", skip_checks=True, stdout=StringIO())

    assert not called, "没拿到锁就不该执行迁移"
    assert "RELEASE_LOCK" not in " ".join(fake.sql), "没拿到锁就不该去释放"


def test_unsupported_backend_fails_loudly(monkeypatch):
    """认不出的后端宁可报错：以前那种「退化成不加锁」是假安全。"""
    monkeypatch.setattr(mod, "connection", types.SimpleNamespace(vendor="sqlite"))

    with pytest.raises(ImproperlyConfigured) as excinfo:
        call_command("migrate_if_needed", skip_checks=True, stdout=StringIO())

    message = str(excinfo.value)
    assert "sqlite" in message
    assert "MIGRATE_ON_START=0" in message
