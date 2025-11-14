from django.urls import path
from .views import (
    ReimbursementRequestView,
    UploadReceiptView,
    ApproveReimbursementView,
    ApproveReimbursementItemView,
    DeclineReimbursementView,
    DeclineReimbursementItemView,
    ExportReimbursement,
    DisbursemntView,
    BulkDisbursementView,

)   
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # List, create, update and submit reimbursement requests
    path('reimbursements/', ReimbursementRequestView.as_view(), name='reimbursement-list-create'),
    path('reimbursements/<int:pk>/<int:item_id>/', ReimbursementRequestView.as_view(), name='reimbursement-update'),
   
    # Upload receipt for a specific reimbursement item
    path('reimbursement-items/receipt/', UploadReceiptView.as_view(), name='upload-receipt'),
    
    # Approve entire reimbursement request
    path('reimbursements/<int:pk>/approve/', ApproveReimbursementView.as_view(), name='approve-reimbursement'),

    # Approve individual reimbursement item
    path('reimbursements/<int:pk>/items/<int:item_id>/approve/', ApproveReimbursementItemView.as_view(), name='approve-reimbursement-item'),

    # Decline entire reimbursement request
    path('reimbursements/<int:pk>/decline/', DeclineReimbursementView.as_view(), name='decline-reimbursement'),

    # Decline individual reimbursement item
    path('reimbursements/<int:pk>/items/<int:item_id>/decline/', DeclineReimbursementItemView.as_view(), name='decline-reimbursement-item'),
    
    # export reimbursements
    path('reimbursements/export/', ExportReimbursement.as_view(), name='export-reimbursements'),

    # Disburse reimbursement
    path('reimbursements/<int:pk>/disburse/', DisbursemntView.as_view(), name='disburse-reimbursement'),
    path('reimbursements/bulk-disburse/', BulkDisbursementView.as_view(), name='bulk-disburse-reimbursements'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
