"""beat 调度条目对账：大屏三条链都必须由内置 beat 投递（不再依赖仓库外调度）。

任务名以装饰器 ``name=`` 为准（``settings`` 里只出现字符串），这里做双向对账：
条目指向的任务确实存在、周期为正、autotask 不比 zabbix 更快。
"""

from django.conf import settings

from ingest import tasks as ingest_tasks


def test_beat_schedule_covers_dashboard_chains():
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule["dashboard-link-cache"]["task"] == getattr(ingest_tasks.refresh_link_cache_task, "name")
    assert schedule["dashboard-collect-zabbix"]["task"] == getattr(ingest_tasks.collect_dashboard, "name")
    assert schedule["dashboard-collect-autotask"]["task"] == getattr(ingest_tasks.collect_dashboard, "name")


def test_beat_schedule_passes_source_args():
    """collect_dashboard 靠 source 区分数据源；漏 args 会在任务里抛 TypeError。"""
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule["dashboard-collect-zabbix"]["args"] == ("zabbix",)
    assert schedule["dashboard-collect-autotask"]["args"] == ("autotask",)


def test_beat_schedule_periods_are_positive():
    """区间型条目周期必须 > 0；crontab 型条目由 cron 表达式自身保证。"""
    for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
        schedule = entry["schedule"]
        if isinstance(schedule, int):
            assert schedule > 0, f"{name} 的周期必须 > 0"


def test_beat_schedule_covers_inspection_chains():
    """巡检两条链（采集调度 / 滚存清理）由内置 beat 投递，任务名与 settings 一致。"""
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule["inspection-dispatch"]["task"] == settings.INSPECTION_DISPATCH_TASK
    assert schedule["inspection-prune"]["task"] == settings.INSPECTION_PRUNE_TASK


def test_autotask_period_not_faster_than_zabbix():
    """外部工单系统比 Zabbix 慢，默认周期不能比设备状态链更短。"""
    schedule = settings.CELERY_BEAT_SCHEDULE
    assert schedule["dashboard-collect-autotask"]["schedule"] >= schedule["dashboard-collect-zabbix"]["schedule"]
