"""分析域模型（包形式）。

历史上这里是单文件 ``analysis/models.py``；dashboard 供数模型加入后按主题拆成子模块，
但**对外导入路径保持不变**：``from analysis.models import AccessFlow`` 等仍可用
（``purge_configs`` / ``policy_expand`` / ``api`` 多处依赖），app_label 也不变。

Django 的 ``AppConfig.import_models`` 只 import ``analysis.models`` 包，模型类由本文件
显式收集；``__module__`` 变成 ``analysis.models.<子模块>`` 不影响
``(app_label, model_name)``，现存 ``0001_initial`` / ``0002_accessflow`` 迁移照样对得上。
注意不能同时留 ``models.py`` 与 ``models/``：Python 导入时包优先，那个文件会被静默忽略。
"""

from .access_flow import AccessFlow
from .dashboard import CollectionRun, DashboardMetric, ItsmCase, LinkTarget, MetricSample
from .internet_analysis import InternetAnalysis

__all__ = [
    "AccessFlow",
    "InternetAnalysis",
    "DashboardMetric",
    "MetricSample",
    "ItsmCase",
    "CollectionRun",
    "LinkTarget",
]
