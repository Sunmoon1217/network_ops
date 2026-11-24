from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework.urls import app_name

from . import auth, preferences, views

router = SimpleRouter(trailing_slash=True)
# 任务工作流：新建任务即投递采集阶段，阶段只读
router.register(r"tasks", views.TaskViewSet, basename="task")
router.register(r"stages", views.StageViewSet, basename="stage")

app_name = "core-api"  # noqa: F811
urlpatterns = [
    # auth / me 是横切入口，留在 /api/ 根下；域资源一律进 /api/core/
    path("auth/register/", auth.register, name="register"),
    path("auth/login/", auth.login, name="login"),
    path("auth/change-password/", auth.changepassword, name="change-password"),
    path("auth/logout/", auth.logout, name="logout"),
    path("me/", auth.me, name="me"),
    # 前端界面偏好（表格列宽等），按用户存取
    path("me/preferences/", preferences.preferences, name="preferences"),
    path("core/integrations/", views.IntegrationHealthView.as_view(), name="integration-health"),
    path("core/", include(router.urls)),
]
