"""按用户保存的前端配置（表格列宽等界面偏好）。

一个接口管三种动词：

- ``GET``  返回当前用户的全部偏好 ``{key: value}``（可 ``?key=`` 只取一条）；
- ``PUT``  按 ``{"key": ..., "value": ...}`` 单条 upsert——**不是全量替换**，
  前端每张表只回写自己那个 key，避免并发页面互相覆盖；
- ``DELETE ?key=`` 删除一条（value 传 ``null`` 也走删除，见下）。

约定 ``value=None`` 即删除：偏好值本身用不到 null（列宽是 ``{列: 宽度}``），用它表达
「清除」省掉一个专门的语义。所有读写都限定 ``request.user``，偏好不跨用户共享。
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import UserPreference

# 与模型 max_length 一致；超长 key 直接 400，不等到数据库才报错
MAX_KEY_LENGTH = 100


def _validate_key(key) -> str | None:
    if not key or not isinstance(key, str):
        return None
    if len(key) > MAX_KEY_LENGTH:
        return None
    return key


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def preferences(request):
    user = request.user

    if request.method == "GET":
        qs = user.preferences.all()
        key = request.query_params.get("key")
        if key:
            qs = qs.filter(key=key)
        return Response({pref.key: pref.value for pref in qs})

    if request.method == "DELETE":
        key = _validate_key(request.query_params.get("key"))
        if key is None:
            return Response({"error": "缺少或非法的 key"}, status=status.HTTP_400_BAD_REQUEST)
        user.preferences.filter(key=key).delete()
        return Response({"key": key, "deleted": True})

    # PUT：单条 upsert
    key = _validate_key(request.data.get("key"))
    if key is None:
        return Response({"error": "缺少或非法的 key"}, status=status.HTTP_400_BAD_REQUEST)
    if "value" not in request.data:
        return Response({"error": "缺少 value"}, status=status.HTTP_400_BAD_REQUEST)

    value = request.data["value"]
    if value is None:
        # null 即清除该条（见模块 docstring）
        user.preferences.filter(key=key).delete()
        return Response({"key": key, "value": None})

    UserPreference.objects.update_or_create(user=user, key=key, defaults={"value": value})
    return Response({"key": key, "value": value})
