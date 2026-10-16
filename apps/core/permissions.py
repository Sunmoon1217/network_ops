"""DRF 权限类。

角色模型（见 ``core.models.User.role``）：

- ``normal``   普通用户：登录后只读（查询）
- ``operator`` 操作员：登录后可读 + 增删改

``IsOperatorOrReadOnly`` 是全局默认权限：读方法（GET / HEAD / OPTIONS）任何已认证用户
都可，写方法（POST / PUT / PATCH / DELETE）要求操作员或超管。登录 / 注册等公开接口仍由
各自的 ``AllowAny`` 覆盖；改自己密码 / 自己偏好这类「自服务」接口保持 ``IsAuthenticated``
（普通用户管理自己的数据，不需要操作员身份）。
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOperatorOrReadOnly(BasePermission):
    """普通用户可读，操作员可读写。"""

    message = "需要操作员权限才能执行该写操作"

    def has_permission(self, request, view):
        # 读方法：已认证即可
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        # 写方法：操作员或超管
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == "operator")
        )
