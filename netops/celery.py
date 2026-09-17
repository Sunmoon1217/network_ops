"""Celery 配置"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netops.settings")

app = Celery("netops")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
