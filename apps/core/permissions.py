"""DRF 权限类。

``IsOperatorOrReadOnly`` 是全局默认权限：读方法任何已认证用户可用，写方法要求操作员
（``role=operator``）或超管。登录 / 注册等公开接口由各自的 ``AllowAny`` 覆盖。
"""

from typing import cast

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User


class IsOperatorOrReadOnly(BasePermission):
    """普通用户可读，操作员可读写。"""

    message = "需要操作员权限才能执行该写操作"

    def has_permission(self, request, view):
        user = cast(User, request.user)
        # 读方法：已认证即可
        if request.method in SAFE_METHODS:
            return bool(user and user.is_authenticated)
        # 写方法：操作员或超管
        return bool(user and user.is_authenticated and (user.is_superuser or user.role == "operator"))
