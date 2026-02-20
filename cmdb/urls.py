from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import *
from cmdb import views

router = SimpleRouter(trailing_slash=True)
router.register(r'devices', DeviceViewSet, basename='device')
router.register(r'configs', DeviceConfigViewSet, basename='config')
router.register(r'virtuals', VirtualServerViewSet, basename='virtual')
router.register(r'interfaces', InterfaceViewSet, basename='interface')

# 包含两种路由格式
urlpatterns = [
    path('index/', views.api_index, name='index'),
    path('', include(router.urls)),
]
