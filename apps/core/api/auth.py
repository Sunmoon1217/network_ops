from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token as DRFToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
    return Response({
        "token": drf_token.key,
        "user": {"id": u.pk, "username": u.username},
    })


@api_view(["POST"])
def logout(request):
    DRFToken.objects.filter(user=request.user).delete()
    return Response({"message": "已登出"})


@api_view(["GET"])
def me(request):
    u = User.objects.get(pk=request.user.pk)
    return Response({
        "id": u.pk,
        "username": u.username,
        "email": u.email,
        "is_staff": u.is_staff,
        "phone": u.phone,
        "avatar": u.avatar,
    })
