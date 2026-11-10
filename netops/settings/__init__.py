"""settings 包入口：base 定义（env 动态项唯一一处）→ 按 DJANGO_ENV 白名单选环境文件。

环境旋钮唯一：DJANGO_ENV（dev 默认 / container / prod），未知值直接拒绝启动；覆盖顺序与
守卫矩阵见 docs/settings.md。DJANGO_SETTINGS_MODULE 恒为 netops.settings。
"""

import os
import sys

from django.core.exceptions import ImproperlyConfigured

from .base import *

# import * 不带下划线开头的名字，但 tests/deploy 直接用 netops.settings._env_or_file，
# 这两个助手必须显式补导出，否则测试 AttributeError。
from .base import _env_list, _env_or_file  # noqa: F401

_ENV = os.environ.get("DJANGO_ENV", "dev")
if _ENV == "dev":
    from .dev import *
elif _ENV == "container":
    from .container import *
elif _ENV == "prod":
    from .prod import *
else:
    raise ImproperlyConfigured(f"未知 DJANGO_ENV={_ENV!r}，可选 dev / container / prod")

APPS_DIR = BASE_DIR / "apps"
# 根目录也在 sys.path 里：根目录下的 llmtools（LLM 工具出口层）以顶层包出现。
# 它通常已由 manage.py / 容器 WORKDIR 带进来，但 gunicorn --chdir、从别处跑 pytest
# 会丢掉它——显式补上，别让出口层的可用性依赖 CWD。
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))
