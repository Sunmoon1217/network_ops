"""项目级 DRF 分页配置。

全站列表接口统一使用数字分页（PageNumberPagination）：

- 默认每页条数由 ``REST_FRAMEWORK["PAGE_SIZE"]`` 提供（50 条）；
- 客户端可通过 ``?page_size=`` 覆盖，但单页最多 500 条，
  避免一次性把整表数据拉进内存；
- 响应结构为 ``{count, next, previous, results}``。

后续如需对大表（ARP/MAC、路由表、子网使用率等时序数据）单独启用游标分页，
可新建 ``CursorPagination`` 子类并在对应 ViewSet 上设置 ``pagination_class``，
但必须显式声明唯一且不可变的 ``ordering``（如 ``("-created_at", "-pk")``）。
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """默认数字分页：每页 50 条，最大 500 条。"""

    page_size_query_param = "page_size"
    max_page_size = 500
