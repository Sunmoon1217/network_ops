"""
URL configuration for netops project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic.base import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    # 支持无尾部斜杠访问 /admin -> /admin/
    path('admin', RedirectView.as_view(url='/admin/')),
    path('api/', include('cmdb.urls')),
    # path('', views.vue_index, name='index'),
    path('check-wal-mode/', views.check_wal_mode, name='check_wal_mode'),

]

#添加静态文件URL配置
if settings.DEBUG:
    # 不要指定document_root参数，让Django自动查找所有静态文件目录
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
# 配置favicon.ico的访问
urlpatterns += [
    path('favicon.ico', views.favicon),
    # catch-all: 排除 admin/, api/, static/ 和 media/ 前缀，防止覆盖这些路由
    re_path(r'^(?!admin/|api/|static/|media/).*$', views.vue_index),
]
