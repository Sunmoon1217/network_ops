"""容器环境（DJANGO_ENV=container，由 env/app.env 注入）：容器与宿主的差异全部由 env 表达。

本文件只留两条守卫：POSTGRES_HOST / REDIS_HOST 必须已注入——base 里默认本机 127.0.0.1，
而 Django 的连接是惰性的，env_file 少一行会拖到首个请求才 connection refused。
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
