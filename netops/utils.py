from rest_framework.pagination import PageNumberPagination

class CustomPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        query_param = request.query_params
        if 'page' not in query_param and 'page_size' not in query_param:
            if queryset.count() < 100:
                return None

        return super().paginate_queryset(queryset, request, view)