"""容器环境（docker compose 的 app / worker）：DJANGO_ENV=container（env/app.env 注入）。

容器与宿主的差异**全部由 env/app.env 的注入表达**（POSTGRES_HOST=db、REDIS_HOST=redis、
*_FILE=/run/secrets/* …），配置读取统一在 base——本文件只留两条守卫：

    POSTGRES_HOST / REDIS_HOST 必须已注入。

它们来自 env_file：文件被误删一行时**启动即拒**，而不是退到 base 的 localhost 默认
——Django 的数据库连接是惰性的，那样要到首个请求才报 connection refused，
故障发现晚一拍。
"""

import os

from django.core.exceptions import ImproperlyConfigured

# 缺哪个一次列全（与 prod 守卫同风格）：env_file 被误删多行时一条消息看全，
# 不做「修一个、再启动、又缺一个」的挤牙膏式失败。
_missing = [key for key in ("POSTGRES_HOST", "REDIS_HOST") if not os.environ.get(key)]
if _missing:
    raise ImproperlyConfigured(
        f"容器环境缺少必须由 env/app.env 注入的变量（共 {len(_missing)} 个）：{', '.join(_missing)}"
    )
