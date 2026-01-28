from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import DeviceViewSet, DeviceConfigViewSet
from cmdb import views

# 创建两个路由器，同时支持带斜杠和不带斜杠的URL
# 1. 不带斜杠的路由器 - 用于 /devices/{id}/config 格式
router = SimpleRouter(trailing_slash=False)
router.register(r'devices', DeviceViewSet, basename='device')
router.register(r'configs', DeviceConfigViewSet, basename='config')

# 2. 带斜杠的路由器 - 用于 /api/devices/ 格式
router_with_slash = SimpleRouter(trailing_slash=True)
router_with_slash.register(r'devices', DeviceViewSet, basename='device')
router_with_slash.register(r'configs', DeviceConfigViewSet, basename='config')

# 包含两种路由格式
urlpatterns = [
    path('index/', views.api_index, name='index'),
    path('', include(router.urls)),
    path('', include(router_with_slash.urls)),
]
