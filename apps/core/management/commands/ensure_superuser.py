"""没有超级用户时创建一个初始管理员（零配置：不读环境变量、不依赖 secret）。

已有超管就跳过；没有则建 ``admin`` 并把随机密码打印在启动日志里；同名但不是超管时
只警告、不自动提权。人工用法：``--username`` / ``--password``（不回显）/ ``--update-password``。
边界与取舍见 handbook/deploy.md「启动三步」。
"""

import secrets
from typing import cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import User

DEFAULT_USERNAME = "admin"


class Command(BaseCommand):
    help = "没有超级用户时创建一个初始管理员，并把随机生成的初始密码打印在启动日志里（零配置）"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=DEFAULT_USERNAME, help=f"管理员用户名（默认 {DEFAULT_USERNAME}）")
        parser.add_argument("--email", default="", help="管理员邮箱（可选）")
        parser.add_argument("--password", default=None, help="显式指定密码；给定时不回显（人工执行用）")
        parser.add_argument("--update-password", action="store_true", help="同名账号已存在时也重置它的密码")

    def handle(self, *args, **options):
        # get_user_model() 返回的是**类**；cast 成 User 实例会走 Manager 的实例描述符
        # （BaseManager.__get__ 的 instance 参数只接受 Options），所以这里标成 type[User]。
        user_model = cast(type[User], get_user_model())
        manager = user_model.objects
        username = options["username"]
        explicit_password = options["password"]
        existing = manager.filter(**{user_model.USERNAME_FIELD: username}).first()

        # 常态分支：已经有超管，而这次调用没要求具体做什么（entrypoint 就是这么调的）
        if existing is None and not explicit_password and not options["update_password"] and manager.filter(is_superuser=True).exists():
            self.stdout.write("[ensure_superuser] 已存在超级用户，跳过")
            return

        if existing is not None and not options["update_password"]:
            if existing.is_superuser:
                self.stdout.write(f"[ensure_superuser] 管理员 {username!r} 已存在，跳过")
            else:
                self.stdout.write(self.style.WARNING(f"[ensure_superuser] {username!r} 已存在但**不是**超级用户，不自动提权。要提权请手工处理（或先删掉该账号再重跑本命令）"))
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
