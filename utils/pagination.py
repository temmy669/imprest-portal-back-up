from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.conf import settings

class DynamicPageSizePagination(PageNumberPagination):
    """
    Custom pagination class that allows dynamic page size via query parameter.
    Falls back to the default PAGE_SIZE from settings if not provided.
    """
    def paginate_queryset(self, queryset, request, view=None):
        # Get page_size from query params, default to settings PAGE_SIZE
        page_size = request.query_params.get('page_size')
        if page_size:
            try:
                page_size = int(page_size)
                # Optional: Set a max limit to prevent abuse
                max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)  # Default max 100
                if page_size > max_page_size:
                    page_size = max_page_size
                self.page_size = page_size
            except ValueError:
                # If invalid, use default
                self.page_size = getattr(settings, 'REST_FRAMEWORK', {}).get('PAGE_SIZE', 10)
        else:
            self.page_size = getattr(settings, 'REST_FRAMEWORK', {}).get('PAGE_SIZE', 10)

        return super().paginate_queryset(queryset, request, view)
