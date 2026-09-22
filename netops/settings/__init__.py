"""settings 包入口：base 定义（env 动态项唯一一处）→ 按 DJANGO_ENV 白名单选环境文件。

- 环境旋钮唯一：**DJANGO_ENV**（dev = 默认 / container / prod），未知值**直接拒绝启动**
  ——拼错（如 prd）不许静默落 dev。
- `DJANGO_SETTINGS_MODULE` 恒为 `netops.settings`：manage/asgi/wsgi/celery 的 setdefault、
  pytest（pyproject.toml）都指包；容器由 env/app.env 注入 `DJANGO_ENV=container`。
- 覆盖顺序：`from .base import *` 先、`from .<env> import *` 后 → 环境文件的少数
  硬差异（prod 的 DEBUG=False、守卫即 import 副作用）胜出；dev 为空壳，无覆盖。
- 另做两件事：把 base 的两个助手暴露到包上（tests/deploy 直接用
  netops.settings._env_or_file）、把 apps/ 加进 sys.path（core/ingest/assets/analysis 以顶层包出现）。
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
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))
