from django.urls import path

from . import trace

urlpatterns = [
    path("trace/", trace.path_trace, name="path-trace"),
    path("trace/route-collect/", trace.route_collect, name="route-collect"),
    path("trace/route-collect-raw/", trace.route_collect_raw, name="route-collect-raw"),
    path("trace/routes/", trace.route_list, name="route-list"),
    path("trace/dns-query/", trace.dns_query, name="dns-query"),
]
