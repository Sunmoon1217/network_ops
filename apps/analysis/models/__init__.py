"""分析域模型包：本文件只做 re-export，模型定义在 ``accessflow`` / ``internet`` /
``dashboard`` 子模块；``from analysis.models import X`` 与 ``app_label`` 保持不变。

不能同时留 ``models.py`` 与 ``models/``：包优先，单文件会被静默忽略。
"""

from .accessflow import AccessFlow
from .dashboard import CollectionRun, DashboardMetric, ItsmCase, LinkTarget, MetricSample
from .internet import InternetAnalysis

__all__ = [
    "AccessFlow",
    "InternetAnalysis",
    "DashboardMetric",
    "MetricSample",
    "ItsmCase",
    "CollectionRun",
    "LinkTarget",
]
