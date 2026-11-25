from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token as DRFToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.api.serializers import ChangePasswordSerializer, RegisterSerializer
from core.models import User


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    """用账号密码换 token。

    必须显式 ``@authentication_classes([])``，否则带已登录 sessionid 时会被 DRF 的
    ``SessionAuthentication`` 拦成 403；原理见 handbook/api.md「认证约定」。
    """
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({"error": "用户名或密码错误"}, status=status.HTTP_401_UNAUTHORIZED)

    drf_token, _ = DRFToken.objects.get_or_create(user=user)

    u = User.objects.get(pk=user.pk)
    return Response(
        {
            "token": drf_token.key,
            "user": {"id": u.pk, "username": u.username},
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def register(request):
    """注册普通账号，成功即返回 token（注册即登录）；只创建普通账号，细节见 handbook/api.md。"""
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    drf_token, _ = DRFToken.objects.get_or_create(user=user)
    return Response(
        {"token": drf_token.key, "user": {"id": user.pk, "username": user.username}},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """登出：任何已登录用户都可，不需要操作员身份（全局默认权限会限写，这里显式放开）。"""
    DRFToken.objects.filter(user=request.user).delete()
    return Response({"message": "已登出"})


@api_view(["GET"])
def me(request):
    u = User.objects.get(pk=request.user.pk)
    return Response(
        {
            "id": u.pk,
            "username": u.username,
            "email": u.email,
            "is_staff": u.is_staff,
            "role": u.role,
            # 派生的写权限（is_superuser 或 role==operator）：前端据此隐藏写入口，
            # 不必在客户端复刻一遍 IsOperatorOrReadOnly 的规则
            "can_write": u.is_operator,
            "phone": u.phone,
            "avatar": u.avatar,
        }
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def changepassword(request):
    """修改密码。"""
    serializer = ChangePasswordSerializer(request.user, data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({"success": True})
