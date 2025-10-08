from django.urls import path
from .views import (
    PurchaseRequestView,
    ApprovePurchaseRequestView,
    DeclinePurchaseRequestView,
    DeclinePurchaseRequestItemView,
    ApprovePurchaseRequestItemView,
    SearchPurchaseRequestView,
    DateRangeFilterView,
    ListApprovedPurchaseRequestView,
    UpdatePurchaseRequestLimit,
    ExportPurchaseRequest
)

urlpatterns = [
    # List and create purchase requests
    path(
        '',
        PurchaseRequestView.as_view(),
        name='purchase-request-list-create'
    ),
    
    # Update a purchase request
    path(
        '<int:pk>/',
        PurchaseRequestView.as_view(),
        name='purchase-request-detail'
    ),

    # Approve a purchase request
    path(
        '<int:pk>/approve/',
        ApprovePurchaseRequestView.as_view(),
        name='approve-purchase-request'
    ),

    # Decline a purchase request
    path(
        '<int:pk>/decline/',
        DeclinePurchaseRequestView.as_view(),
        name='decline-purchase-request'
    ),
    
    path(
        '<int:pk>/items/<int:item_id>/decline/',
        DeclinePurchaseRequestItemView.as_view(),
        name='decline-purchase-request-item'
    ),
    
    path(
        '<int:pk>/items/<int:item_id>/approve/',
        ApprovePurchaseRequestItemView.as_view(),
        name='approve-purchase-request-item'
    ),
    
    path(
        'search/',
        SearchPurchaseRequestView.as_view(),
        name='search-purchase-request'
    ),
    
    path(
        'filter/date-range/',
        DateRangeFilterView.as_view(),
        name='date-range-filter'
    ),
    
    path('approved-purchase-requests/',
        ListApprovedPurchaseRequestView.as_view(),
        name='list-approved-purchase-requests'  
    ),
    
    path('limit-config/',
         UpdatePurchaseRequestLimit.as_view(), 
         name='update-purchase-request-limit'),
    
    path('export-purchase-requests/', 
         ExportPurchaseRequest.as_view(), 
         name='export-purchase-requests'),
]
