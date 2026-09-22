from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework.urls import app_name

from . import auth, preferences, views

router = SimpleRouter(trailing_slash=True)
# 任务工作流：列表 / 详情 / 新建（新建即投递采集阶段）/ 取消，阶段只读。
# 此前这两个模型只有定义、没有任何接口，于是 celery 那条链路在产品里不可达。
router.register(r"tasks", views.TaskViewSet, basename="task")
router.register(r"stages", views.StageViewSet, basename="stage")

app_name = "core-api"  # noqa: F811
urlpatterns = [
    path("auth/register/", auth.register, name="register"),
    path("auth/login/", auth.login, name="login"),
    path("auth/change-password/", auth.changepassword, name="change-password"),
    path("auth/logout/", auth.logout, name="logout"),
    path("me/", auth.me, name="me"),
    # 前端配置（表格列宽等界面偏好）：按用户存取，语义见 preferences 模块
    path("me/preferences/", preferences.preferences, name="preferences"),
    path("", include(router.urls)),
]
