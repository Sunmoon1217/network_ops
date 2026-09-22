"""生产环境（DJANGO_ENV=prod）：唯一不走环境变量的硬差异 + 关键 env 必填守卫（fail loud）。

- `DEBUG = False` 是本文件唯一的「按环境硬改」——生产写死，**不吃 DJANGO_DEBUG 后门**；
- 守卫查 `os.environ` 的**原始值**：base 的动态读取带默认值兜底（HOSTS 默认 `*`、
  HOST 默认 localhost、密钥有开发期 fallback），只有在这里检查「有没有设置」，
  才能在**启动时**把配置缺失拦下来，而不是等首个请求连库/被攻击面暴露才发现。

与 dev/container 的区别不是「读不读环境变量」，而是**缺了会怎样**：
那两个缺配置有可用默认值，prod 没有——配错就在 import 本文件时炸。
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

if not os.environ.get("POSTGRES_HOST"):
    _errors.append("POSTGRES_HOST —— 数据库地址（生产没有 localhost 默认）")

if not (os.environ.get("POSTGRES_PASSWORD_FILE") or os.environ.get("POSTGRES_PASSWORD")):
    _errors.append("POSTGRES_PASSWORD_FILE（容器 secrets）或 POSTGRES_PASSWORD —— 数据库凭据")

if not os.environ.get("REDIS_HOST"):
    _errors.append("REDIS_HOST —— Redis 地址（生产没有 localhost 默认）")

if _errors:
    raise ImproperlyConfigured(
        "生产环境配置缺失/非法（共 {n} 项，一次列全）：\n{n_lines}".format(
            n=len(_errors), n_lines="\n".join(f"  - {item}" for item in _errors)
        )
    )
