"""设备管理用户保存器"""

from logging import getLogger

from .base import BaseSaver, as_list

logger = getLogger(__name__)

# H3C 的 local-user class → 模型权限级别
_CLASS_TO_PRIVILEGE = {
    "manage": "admin",
    "network": "operator",
    "read": "readonly",
}


def _join(value) -> str:
    """把 TTP 产出的 list / dict / 标量统一拼成空格分隔的文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return " ".join(str(item) for item in as_list(value))


class DeviceAccountSaver(BaseSaver):
    """设备管理用户保存器。

    只消费 H3C 的 ``local_users``。同一批产出里的 ``ssh`` 是服务开关
    （``ssh server enable``）、``roles`` 是角色定义、A10 的 ``account`` 是空 group，
    都不产生账号记录，因此不作为 Saver 的 key。
    """

    device_types = ["switch"]
    keys = ["local_users"]
    model_paths = ["assets.models.DeviceAccount"]

    def _save(self, device, parsed_data: dict) -> tuple[int, int]:
        from assets.models import DeviceAccount
        from assets.serializers.views import DeviceAccountSerializer

        created, updated = 0, 0
        for user in as_list(parsed_data.get("local_users")):
            username = user.get("username")
            if not username:
                continue
            is_new = self.upsert(
                DeviceAccountSerializer,
                DeviceAccount,
                device,
                {"username": username},
                {
                    "username": username,
                    "auth_type": "password" if user.get("password") else "ssh-key",
                    "privilege": self._privilege(user),
                    "description": self._describe(user),
                },
            )
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
        return (created, updated)

    def _privilege(self, user: dict) -> str:
        """H3C 用 ``class`` 表达级别，部分版本改用 ``authorization-attribute user-role``。"""
        user_class = user.get("user_class")
        if user_class:
            mapped = _CLASS_TO_PRIVILEGE.get(str(user_class).lower())
            if mapped:
                return mapped
        roles = _join(user.get("role"))
        if "read" in roles:
            return "readonly"
        if "admin" in roles:
            return "admin"
        return "operator"

    def _describe(self, user: dict) -> str:
        parts = []
        service_type = _join(user.get("service_type"))
        if service_type:
            parts.append(f"service-type: {service_type}")
        roles = _join(user.get("role"))
        if roles:
            parts.append(f"role: {roles}")
        return "; ".join(parts)[:255]
