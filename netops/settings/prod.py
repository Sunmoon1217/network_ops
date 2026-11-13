"""生产环境（DJANGO_ENV=prod）：DEBUG 硬覆盖 + 关键 env 必填守卫（fail loud）。

与 dev/container 的区别不是「读不读环境变量」，而是缺了会怎样：那两个缺配置有可用默认值，
prod 没有——配错就在 import 本文件时炸。守卫查 os.environ 原始值（base 的读取带默认值兜底），
否则「没设置」会被兜底掩盖。守卫清单见 handbook/settings.md。
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import _env_list

# 硬覆盖：生产写死关闭 DEBUG（环境变量 DJANGO_DEBUG 对 prod 无效）。
DEBUG = False

# 守卫收集全部问题后**一次报全**——缺 5 个就一条消息列 5 个，
# 不做「修一轮、再启动、又报下一个」的挤牙膏式失败。
_errors: list[str] = []

if not os.environ.get("DJANGO_SECRET_KEY"):
    _errors.append("DJANGO_SECRET_KEY —— 稳定密钥（各环境一个，泄漏即轮换）")

# base 对未设置时默认 `*`，这里用 default="" 重算来区分「设了空」与「设了 *」：
# 未设置 → [] → 记错；设空 → [] → 记错；设 `*` → 下面第二条记错。
_hosts = _env_list("DJANGO_ALLOWED_HOSTS")
if not _hosts:
    _errors.append("DJANGO_ALLOWED_HOSTS —— 逗号分隔的域名/IP（例如 netops.example.com,10.0.0.5）")
elif "*" in _hosts:
    _errors.append("DJANGO_ALLOWED_HOSTS —— 生产不允许 '*'，请写具体域名/IP")

if not os.environ.get("DB_HOST"):
    _errors.append("DB_HOST —— 数据库地址（生产不沿用本机默认）")

if not (os.environ.get("DB_PASSWORD_FILE") or os.environ.get("DB_PASSWORD")):
    _errors.append("DB_PASSWORD_FILE（容器 secrets）或 DB_PASSWORD —— 数据库凭据")

if not os.environ.get("REDIS_HOST"):
    _errors.append("REDIS_HOST —— Redis 地址（生产不沿用本机默认）")

if _errors:
    raise ImproperlyConfigured(
        "生产环境配置缺失/非法（共 {n} 项，一次列全）：\n{n_lines}".format(
            n=len(_errors), n_lines="\n".join(f"  - {item}" for item in _errors)
        )
    )
