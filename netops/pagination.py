"""全站 DRF 分页：数字分页，默认 50 条/页，?page_size= 可覆盖（上限 500）。

响应结构 {count, next, previous, results}；时序大表若需游标分页，
在对应 ViewSet 上单独指定 pagination_class 并显式声明不可变的 ordering。
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """默认数字分页：每页 50 条，最大 500 条。"""

    page_size_query_param = "page_size"
    max_page_size = 500
