from django.urls import path
from .views import (
    PurchaseRequestView,
    ApprovePurchaseRequestView,
    DeclinePurchaseRequestView,
    DeclinePurchaseRequestItemView,
    ApprovePurchaseRequestItemView,
)

urlpatterns = [
    # List and create purchase requests
    path(
        '',
        PurchaseRequestView.as_view(),
        name='purchase-request-list-create'
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
        'purchase-requests/<int:pk>/items/<int:item_id>/decline/',
        DeclinePurchaseRequestItemView.as_view(),
        name='decline-purchase-request-item'
    ),
    
    path(
        'purchase-requests/<int:pk>/items/<int:item_id>/approve/',
        ApprovePurchaseRequestItemView.as_view(),
        name='approve-purchase-request-item'
    ),
]
