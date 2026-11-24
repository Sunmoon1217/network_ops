"""settings 包入口：base 打底 → 按 DJANGO_ENV 白名单选环境文件。

DJANGO_ENV 只有 dev / container / prod，未知值拒绝启动；覆盖顺序与守卫矩阵见 handbook/settings.md。
这里还把 BASE_DIR 与 apps/ 插进 sys.path，让 llmtools 与各域以顶层包出现。
"""

import os
import sys

from django.core.exceptions import ImproperlyConfigured

from .base import *

# import * 不带下划线名字，但 tests/deploy 直接用这两个助手，必须显式补导出。
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
# 显式补根目录，避免出口层可用性依赖 CWD（gunicorn --chdir、从别处跑 pytest）。
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))
