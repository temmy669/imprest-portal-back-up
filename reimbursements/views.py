from collections import Counter
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Reimbursement
from .serializers import *
from utils.permissions import ViewReimbursementRequest, SubmitReimbursementRequest
from helpers.response import CustomResponse
from users.auth import JWTAuthenticationFromCookie
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
import os
from django.conf import settings


class ReimbursementRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), ViewReimbursementRequest()]
        elif self.request.method == 'POST':
            return [IsAuthenticated(), SubmitReimbursementRequest()]
        return [IsAuthenticated()]

    def get(self, request):
        user = request.user
        queryset = Reimbursement.objects.all()

        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__region__area_manager=user)

        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Status counts for ALL matching results (not just current page)
        status_count_dict = dict(Counter(queryset.values_list('status', flat=True)))

        serializer = ReimbursementSerializer(paginated_queryset, many=True)

        return CustomResponse(
            True,
            "Filtered reimbursement requests retrieved",
            200,
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
                "status_counts": status_count_dict,
            }
        )

    def post(self, request):
        serializer = ReimbursementSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            reimbursement = serializer.save(requester=request.user)
            
            # Check if any item requires receipt
            items_requiring_receipt = [item.item_name for item in reimbursement.items.all() if item.requires_receipt]
            message = "Reimbursement Request Created Successfully"
            if items_requiring_receipt:
                message += f". Please upload receipts for the following items: {', '.join(items_requiring_receipt)}."

            return CustomResponse(True, message, 201, ReimbursementSerializer(reimbursement).data)
        
        return CustomResponse(False, serializer.errors, 400)

    def put(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        serializer = ReimbursementUpdateSerializer(
            reimbursement, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "Reimbursement Request Updated Successfully", 200, serializer.data)
        return CustomResponse(False, serializer.errors, 400)


class UploadReceiptView(APIView):
    """
    Upload a receipt for a single reimbursement item.
    POST /reimbursement-items/<int:item_id>/receipt/
    form-data: receipt=<file>
    """
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, item_id):
        item = get_object_or_404(
            ReimbursementItem,
            pk=item_id,
            reimbursement__requester=request.user  # ensure ownership
        )

        if "receipt" not in request.FILES:
            return CustomResponse(False, "No file uploaded", 400)

        receipt_file = request.FILES["receipt"]

        # Save using the model FileField's storage (upload_to='receipts/')
        # This is the simplest and most robust way.
        item.receipt.save(receipt_file.name, receipt_file, save=True)

        return CustomResponse(
            True,
            "Receipt uploaded successfully",
            200,
            {
                "item_id": item.id,
                "reimbursement_id": item.reimbursement,
                "requires_receipt": item.requires_receipt,
                "receipt_url": request.build_absolute_uri(item.receipt.url),
            }
        )
        
class SubmitReimbursementView(APIView):
    """
    Finalize a reimbursement (move from draft to pending).
    POST /reimbursements/<int:pk>/submit/
    """
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        reimbursement = get_object_or_404(
            Reimbursement,
            pk=pk,
            requester=request.user
        )

        # Find items missing required receipts
        missing_qs = reimbursement.items.filter(
            requires_receipt=True
        ).filter(receipt__isnull=True).union(
            reimbursement.items.filter(requires_receipt=True, receipt="")
        )

        if missing_qs.exists():
            missing = [
                {
                    "item_id": it.id,
                    "item_name": it.item_name,
                    "unit_price": str(it.unit_price),
                    "quantity": it.quantity,
                    "item_total": str(it.item_total),
                }
                for it in missing_qs
            ]
            return CustomResponse(
                False,
                "One or more items require a receipt before submission.",
                400,
                {"items_missing_receipts": missing}
            )

        # All good: finalize
        reimbursement.is_draft = False
        reimbursement.status = "pending"  # or your specific pending status
        reimbursement.save(update_fields=["is_draft", "status"])

        data = ReimbursementSerializer(reimbursement).data
        return CustomResponse(True, "Reimbursement submitted for approval", 200, data)