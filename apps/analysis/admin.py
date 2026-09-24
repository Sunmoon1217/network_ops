# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import InternetAnalysis


@admin.register(InternetAnalysis)
class InternetAnalysisAdmin(admin.ModelAdmin):
    # result 是整份分析结果的大 JSON，不进列表；详情页查看
    list_display = ("id", "device", "duration_ms", "analyzed_at")
    list_filter = (("device", admin.RelatedOnlyFieldListFilter), "analyzed_at")
    search_fields = ("device__hostname",)
    autocomplete_fields = ("device",)
    list_select_related = ("device",)
    date_hierarchy = "analyzed_at"
