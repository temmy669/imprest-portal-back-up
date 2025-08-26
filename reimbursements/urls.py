from django.urls import path
from .views import (
    ReimbursementRequestView,
    UploadReceiptView,
    SubmitReimbursementView,
    ApproveReimbursementView,
    ApproveReimbursementItemView,
    DeclineReimbursementView,
    DeclineReimbursementItemView,
    InternalControlReimbursementView,
)
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # List, create, or update reimbursement requests
    path('reimbursements/', ReimbursementRequestView.as_view(), name='reimbursement-list-create'),
    path('internal-control-re/', InternalControlReimbursementView.as_view(), name='internal-control-re'),
    path('reimbursements/<int:pk>/', ReimbursementRequestView.as_view(), name='reimbursement-update'),
    
    # Submit a reimbursement (requires reimbursement pk)
    path('reimbursements/<int:pk>/submit/', SubmitReimbursementView.as_view(), name='submit-reimbursement'),

    # Upload receipt for a specific reimbursement item
    path('reimbursement-items/<int:item_id>/receipt/', UploadReceiptView.as_view(), name='upload-receipt'),
    
    # Approve entire reimbursement request
    path('reimbursements/<int:pk>/approve/', ApproveReimbursementView.as_view(), name='approve-reimbursement'),

    # Approve individual reimbursement item
    path('reimbursements/<int:pk>/items/<int:item_id>/approve/', ApproveReimbursementItemView.as_view(), name='approve-reimbursement-item'),

    # Decline entire reimbursement request
    path('reimbursements/<int:pk>/decline/', DeclineReimbursementView.as_view(), name='decline-reimbursement'),

    # Decline individual reimbursement item
    path('reimbursements/<int:pk>/items/<int:item_id>/decline/', DeclineReimbursementItemView.as_view(), name='decline-reimbursement-item'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
