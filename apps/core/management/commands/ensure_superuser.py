"""没有超级用户时创建一个初始管理员——**零配置**：不读环境变量、不依赖密钥文件、不动 compose。

由 ``docker/entrypoint.sh`` 在跑完迁移之后、起 gunicorn 之前调用，目标是**首次部署不做任何配置
就有管理员可用**，而日常重启是无操作：

* 库里**已经有超级用户** → 打印一行跳过（这是常态），不碰任何账号。
* **没有**超级用户 → 创建 ``--username``（默认 ``admin``），密码随机生成
  （``secrets.token_urlsafe()``）并**直接打印在启动日志里**：
  ``已创建初始管理员 'admin'，初始密码：xxxx``——照着 ``docker compose logs app`` 抄下来就能登录，
  登录后请立即改密码。
* 同名账号存在但**不是**超级用户 → 只警告、不自动提权（静默把普通账号变超管是安全事故）。

人工用法（不经过 entrypoint）：``--password`` 显式指定密码（此时**不回显**）、``--username`` /
``--email`` 换账号、``--update-password`` 重置已有账号的密码（忘了密码时用，重置后的随机密码同样
打印在日志里）。

为什么不用 ``DJANGO_SUPERUSER_*`` 环境变量或 docker secrets：初始管理员属于「零配置起步」那一环，
挂到环境变量 / compose / secrets 上等于要求每台部署机先准备一份配置，而且这些值一旦进了环境变量就会
出现在 ``docker inspect``、``/proc/1/environ`` 里。随机密码 + 一次性回显不需要任何配置；代价是密码会
进容器日志，所以它只在这个账号**首次被创建**（或显式重置）时出现，且应当立刻改掉。
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEFAULT_USERNAME = "admin"


class Command(BaseCommand):
    help = "没有超级用户时创建一个初始管理员，并把随机生成的初始密码打印在启动日志里（零配置）"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=DEFAULT_USERNAME, help=f"管理员用户名（默认 {DEFAULT_USERNAME}）")
        parser.add_argument("--email", default="", help="管理员邮箱（可选）")
        parser.add_argument("--password", default=None, help="显式指定密码；给定时不回显（人工执行用）")
        parser.add_argument("--update-password", action="store_true", help="同名账号已存在时也重置它的密码")

    def handle(self, *args, **options):
        user_model = get_user_model()
        manager = user_model._default_manager
        username = options["username"]
        explicit_password = options["password"]
        existing = manager.filter(**{user_model.USERNAME_FIELD: username}).first()

        # 常态分支：已经有超管，而这次调用没要求具体做什么（entrypoint 就是这么调的）
        if (
            existing is None
            and not explicit_password
            and not options["update_password"]
            and manager.filter(is_superuser=True).exists()
        ):
            self.stdout.write("[ensure_superuser] 已存在超级用户，跳过")
            return

        if existing is not None and not options["update_password"]:
            if existing.is_superuser:
                self.stdout.write(f"[ensure_superuser] 管理员 {username!r} 已存在，跳过")
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"[ensure_superuser] {username!r} 已存在但**不是**超级用户，不自动提权。"
                        f"要提权请手工处理（或先删掉该账号再重跑本命令）"
                    )
                )
            return

        password = explicit_password or secrets.token_urlsafe(18)
        if existing is None:
            fields = {user_model.USERNAME_FIELD: username}
            if "email" in user_model.REQUIRED_FIELDS:
                fields["email"] = options["email"]
            manager.create_superuser(password=password, **fields)
            what = f"已创建初始管理员 {username!r}"
        else:
            existing.set_password(password)
            existing.save(update_fields=["password"])
            what = f"已重置 {username!r} 的密码"

        if explicit_password:
            self.stdout.write(f"[ensure_superuser] {what}（密码由 --password 指定，未回显）")
            return
        self.stdout.write(self.style.SUCCESS(f"[ensure_superuser] {what}，初始密码：{password}"))
        self.stdout.write(self.style.WARNING("[ensure_superuser] 请登录后立即修改密码"))
