from django.urls import path
from .views import ReimbursementRequestView, UploadReceiptView, SubmitReimbursementView

urlpatterns = [
    # List, create, or update reimbursement requests
    path('reimbursements/', ReimbursementRequestView.as_view(), name='reimbursement-list-create'),
    path('reimbursements/<int:pk>/', ReimbursementRequestView.as_view(), name='reimbursement-update'),
    
   # Submit a reimbursement (requires reimbursement pk)
    path('reimbursements/<int:pk>/submit/', SubmitReimbursementView.as_view(), name='submit-reimbursement'),

    # Upload receipt for a specific reimbursement item
    path('reimbursement-items/<int:item_id>/receipt/', UploadReceiptView.as_view(), name='upload-receipt'),
]
