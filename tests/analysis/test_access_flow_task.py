"""访问流重建任务（analysis.rebuild_access_flows）的契约。

守护四点：

- **任务名三处一致**：settings.ACCESS_FLOW_TASK（唯一定义处）== 任务装饰器 name ==
  CELERY_TASK_ROUTES 的 key——ingest 的投递触点只认字符串，改名不同步这里就红；
- **只在本任务上开 acks_late**：worker 崩溃任务能重投；但绝不能泄漏成全局设置
  （现有采集/解析/存储三阶段任务的行为不许被顺手改掉）；
- **独立队列路由**：access_flow 与 celery（默认队列）隔离，堵了不拖垮别的任务；
- **背压与锁竞争走 self.retry 而不是 sleep**：发现下游积压/锁被占就立刻结束任务
  释放 worker 进程（在任务里等待会占死进程、把整个执行池堵瘫）。
"""

from contextlib import contextmanager

import pytest
from celery.exceptions import Retry
from django.conf import settings

from analysis.tasks import rebuild_access_flows
from ingest.tasks import run_collection_stage, run_config_storage


def test_task_name_matches_settings_and_routes():
    """任务名的三处对账：settings 常量、装饰器 name、路由 key 必须是同一个字符串"""
    assert settings.ACCESS_FLOW_TASK == "analysis.rebuild_access_flows"
    assert rebuild_access_flows.name == settings.ACCESS_FLOW_TASK
    assert settings.CELERY_TASK_ROUTES[settings.ACCESS_FLOW_TASK] == {"queue": "access_flow"}


def test_acks_late_is_scoped_to_rebuild_task_only():
    """acks_late 是任务级的：只给重建任务开，既有任务与全局配置保持原样"""
    assert rebuild_access_flows.acks_late is True
    assert rebuild_access_flows.reject_on_worker_lost is True
    assert not run_collection_stage.acks_late, "既有任务不该被顺手改成 acks_late"
    assert not run_config_storage.acks_late
    assert getattr(settings, "CELERY_TASK_ACKS_LATE", None) is None, "不许用全局设置代替任务级"


def test_backpressure_releases_task_via_retry(monkeypatch):
    """队列积压超阈值 → self.retry（任务结束、进程释放），而不是在任务里等待"""
    monkeypatch.setattr("analysis.access_stream.backlog", lambda: settings.ACCESS_FLOW_MAX_QUEUE + 1)

    with pytest.raises(Retry):
        rebuild_access_flows(999999)


def test_busy_lock_releases_task_via_retry(monkeypatch):
    """同设备锁被占（acks_late 重投撞上原件）→ 同样立刻退出重试"""
    monkeypatch.setattr("analysis.access_stream.backlog", lambda: 0)

    @contextmanager
    def _busy(_device_id, timeout=600):
        yield False

    monkeypatch.setattr("analysis.access_stream.device_lock", _busy)

    with pytest.raises(Retry):
        rebuild_access_flows(999999)


def test_backlog_threshold_is_configurable():
    """背压阈值来自 settings（env 注入），有默认值且是整数"""
    assert isinstance(settings.ACCESS_FLOW_MAX_QUEUE, int)
    assert settings.ACCESS_FLOW_MAX_QUEUE > 0
