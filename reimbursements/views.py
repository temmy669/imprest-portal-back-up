from collections import Counter
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import *
from .serializers import *
from utils.permissions import ViewReimbursementRequest, SubmitReimbursementRequest, ApproveReimbursementRequest, DeclineReimbursementRequest
from helpers.response import CustomResponse
from users.auth import JWTAuthenticationFromCookie
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
import os
from django.conf import settings
from django.utils import timezone


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
                "reimbursement_id": item.reimbursement.id,
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
    
    
class ApproveReimbursementView(APIView):
    
    # Approve a reimbursement request and its items
    def post(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        if reimbursement.status != 'pending':
            return CustomResponse(False, "Reimbursement is not pending", 400)

        reimbursement.status = 'approved'
        reimbursement_items = reimbursement.items.all()

        # Approve all related items
        reimbursement_items.update(status='approved')

        if request.user.role.name == 'Area Manager':
            reimbursement.area_manager = request.user
            reimbursement.area_manager_approved_at = timezone.now()
        elif request.user.role.name == 'Internal Control' and reimbursement.area_manager:
            reimbursement.internal_control = request.user
            reimbursement.internal_control_approved_at = timezone.now()
        reimbursement.save()
        
        name = ""
        if request.user.role.name == 'Area Manager':
            name = "Area Manager"
            
        elif request.user.role.name == 'Internal Control':
            name = "Internal Control"
        
        message = f"Reimbursement approved by {name} successfully"

        return CustomResponse(True, message, 200)
    

class ApproveReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]
    
    #Approve items in a reimbursement request
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, request=re)

        # Object-level permission check
        self.check_object_permissions(request, re)

        if item.status == 'approved':
            return CustomResponse(False, 'Item is already approved.', 400)
        
        item.status = 'approved'
        item.save()

        items = re.items.all()


        # Check if any item is declined
        if any(i.status == 'declined' for i in items):
            re.status = 'declined'
            if request.user.role.name == "Area Manager":
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
            elif request.user.role.name == "Internal Control":
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()
            re.save()
            
         # Check if all items are approved
        elif all(i.status == 'approved' for i in items):
            re.status = 'approved'
            if request.user.role.name == "Area Manager":
                re.area_manager = request.user
                re.area_manager_approved_at = timezone.now()
            elif request.user.role.name == "Internal Control":
                re.internal_control = request.user
                re.internal_control_approved_at = timezone.now()
            re.save()

        return CustomResponse(True,
            {
                'status': 'approved',
                'item_id': item.id
            },
            200
        )
        
        
class DeclineReimbursementRequest(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk):
        re = get_object_or_404(Reimbursement, pk=pk)

        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)

        if request.user.role.name == "Internal Control":
            # Send back to Area Manager as pending
            re.status = "pending"
            re.internal_control = request.user
            re.internal_control_declined_at = timezone.now()
        elif request.user.role.name == "Area Manager":
            # Final decline
            re.status = "declined"
            re.area_manager = request.user
            re.area_manager_declined_at = timezone.now()

            # Update all items to declined (only final decline)
            re.items.update(status="declined")

        re.save()

        # Create decline comment
        ReimbursementComment.objects.create(
            reimbursement=re,
            author=request.user,
            text=comment_text
        )

        return CustomResponse(
            True,
            {"status": re.status, "comment": comment_text},
            200
        )


class DeclineReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)

        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)

        if item.status == 'declined':
            return CustomResponse(False, "Item is already declined", 400)

        # Decline this item
        item.status = 'declined'
        item.save()

        items = re.items.all()

        if any(i.status == 'pending' for i in items):
            # Some items still pending → request remains pending
            re.status = "pending"
        elif all(i.status != 'pending' for i in items):
            # No more pending items
            if request.user.role.name == "Internal Control":
                # IC decline → send back as pending
                re.status = "pending"
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()
            elif request.user.role.name == "Area Manager":
                # Final decline
                re.status = "declined"
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()

        re.save()

        # Save comment
        ReimbursementComment.objects.create(
            reimbursement=re,
            author=request.user,
            text=comment_text
        )

        return CustomResponse(
            True,
            {
                "status": re.status,
                "item_id": item.id,
                "comment": comment_text
            },
            200
        )
