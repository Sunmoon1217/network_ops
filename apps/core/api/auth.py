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

    **必须显式 `@authentication_classes([])`**：默认认证类里有 `SessionAuthentication`，
    而 DRF 的 `SessionAuthentication.authenticate()` 一旦发现请求带着**已认证的 session**
    就会调用 `enforce_csrf(request)`——这条路径是 DRF 自己发起的，绕开中间件层面的
    `csrf_exempt`（`APIView.as_view()` 本就对整个视图做了 csrf_exempt），于是只要浏览器
    里登录过 `/admin/`（带着 `sessionid`），这个接口就 403：

        {"detail": "CSRF Failed: CSRF cookie not set."}

    实测表现是同一个地址 `localhost:8000` 打不开、`127.0.0.1:8000` 却能登录——因为 cookie
    按 host 存，换 IP 就带不上了。而本接口不需要任何身份，也就没有需要 CSRF 保护的东西
    （真正的风险是「第三方页面借用已登录用户的身份」，这里不存在），所以直接把认证关掉，
    不依赖调用方别带 cookie。
    """
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({"error": "用户名或密码错误"}, status=status.HTTP_401_UNAUTHORIZED)

    # 使用 DRF 内置 Token 模型
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
    """注册一个**普通账号**，成功即返回 token（注册即登录，前端不必再走一次登录）。

    这是与 ``login`` 同一类的公开接口，所以同样必须显式 ``@authentication_classes([])``：
    否则浏览器带着「已登录的 sessionid」打过来时，DRF 的 ``SessionAuthentication`` 会自己调用
    ``enforce_csrf()`` 返回 403——这条路径绕开中间件层的 ``csrf_exempt``，机制与实测详见
    ``login`` 的注释（换 host 就好了那种假象）。

    权限完全由服务端决定：``RegisterSerializer.create()`` 走 ``create_user``，``is_staff`` /
    ``is_superuser`` 都是 False，且请求里根本没有能影响它们的字段。注册开放、不做邮箱验证或审批，
    要收紧（例如加开关 / 邀请码 / 管理员审批）就在这里加校验。
    """
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    drf_token, _ = DRFToken.objects.get_or_create(user=user)
    return Response(
        {"token": drf_token.key, "user": {"id": user.pk, "username": user.username}},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def logout(request):
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
