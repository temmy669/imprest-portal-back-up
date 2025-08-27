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


from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from collections import Counter
from datetime import datetime

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

        # Role-based restrictions
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__in=user.assigned_stores.all())

        # Filters from query params
        area_manager_id = request.query_params.get("area_manager")
        store_ids = request.query_params.getlist("stores")  
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")
        search = request.query_params.get("search")
        search_query = request.query_params.get("q", "").strip()


        # Area Manager filter
        if area_manager_id:
           queryset = queryset.filter(store__assigned_users__id=area_manager_id)

                                       

        # Store filter
        if store_ids:
            queryset = queryset.filter(store_id__in=store_ids)

        # Date range filter
        if start_date:
            try:
                queryset = queryset.filter(created_at__date__gte=datetime.strptime(start_date, "%Y-%m-%d").date())
            except ValueError:
                pass
        if end_date:
            try:
                queryset = queryset.filter(created_at__date__lte=datetime.strptime(end_date, "%Y-%m-%d").date())
            except ValueError:
                pass

        # Status filter
        if status:
            queryset = queryset.filter(status=status)

        # Search filter (by requester name)
        if search:
            queryset = queryset.filter(
                Q(requester__first_name__icontains=search) |
                Q(requester__last_name__icontains=search) |
                Q(requester__name__icontains=search)  
            )
        
        # Special RR-XXXX search (takes priority if provided)
        if search_query:
            if search_query.upper().startswith("RR-"):
                try:
                    request_id = int(search_query.upper().replace("RR-", ""))
                    queryset = queryset.filter(id=request_id)
                except ValueError:
                    return CustomResponse(False, "Invalid request ID format. Expected RR-XXXX", 400)
            else:
                return CustomResponse(False, "Only RR-XXXX search is supported in 'q'", 400)


        # Pagination
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Calculate status counts for just this page
        status_list = [obj.status for obj in (paginated_queryset or [])]
        status_count_dict = dict(Counter(status_list))
        
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

class InternalControlReimbursementView(APIView):
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
        
        queryset = queryset.filter(area_manager_approved_at__isnull=False)
    
        # Filters from query params
        area_manager_id = request.query_params.get("area_manager")
        store_ids = request.query_params.getlist("stores")  
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")
        search = request.query_params.get("search")
        search_query = request.query_params.get("q", "").strip()


        # Area Manager filter
        if area_manager_id:
           queryset = queryset.filter(store__assigned_users__id=area_manager_id)

                                       
        # Store filter
        if store_ids:
            queryset = queryset.filter(store_id__in=store_ids)

        # Date range filter
        if start_date:
            try:
                queryset = queryset.filter(created_at__date__gte=datetime.strptime(start_date, "%Y-%m-%d").date())
            except ValueError:
                pass
        if end_date:
            try:
                queryset = queryset.filter(created_at__date__lte=datetime.strptime(end_date, "%Y-%m-%d").date())
            except ValueError:
                pass

        # Search filter (by requester name)
        if search:
            queryset = queryset.filter(
                Q(requester__first_name__icontains=search) |
                Q(requester__last_name__icontains=search) |
                Q(requester__name__icontains=search)  
            )
        
        # Special RR-XXXX search (takes priority if provided)
        if search_query:
            if search_query.upper().startswith("RR-"):
                try:
                    request_id = int(search_query.upper().replace("RR-", ""))
                    queryset = queryset.filter(id=request_id)
                except ValueError:
                    return CustomResponse(False, "Invalid request ID format. Expected RR-XXXX", 400)
            else:
                return CustomResponse(False, "Only RR-XXXX search is supported in 'q'", 400)


        # Pagination
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Calculate status counts for just this page
        status_list = [obj.internal_control_status for obj in (paginated_queryset or [])]
        status_count_dict = dict(Counter(status_list))
        
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
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]
    
    # Approve a reimbursement request and its items
    def post(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        reimbursement_items = reimbursement.items.all()
        name = ""
        
        if request.user.role.name == "Area Manager":
            if reimbursement.status != 'pending':
                return CustomResponse(False, "Reimbursement is not pending", 400)
            
            reimbursement.status = 'approved'
            reimbursement.area_manager = request.user
            reimbursement.area_manager_approved_at = timezone.now()
            name = "Area Manager"
            
        elif request.user.role.name == "Internal Control":
            if reimbursement.internal_control_status != 'pending':
                return CustomResponse(False, "Reimbursement is not pending", 400)
            
            reimbursement.internal_control_status = "approved"
            reimbursement.internal_control = request.user
            reimbursement.internal_control_approved_at = timezone.now()
            name = "Internal Control"
        
        reimbursement.save()
       
        # Approve all related items
        reimbursement_items.update(status='approved')
        
        message = f"Reimbursement approved by {name} successfully"

        return CustomResponse(True, message, 200)
    

class ApproveReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]
    
    #Approve items in a reimbursement request
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)
        items = re.items.all()
        
        # Object-level permission check
        self.check_object_permissions(request, re)
        
        if request.user.role.name == "Area Manager":
            if item.status == 'approved':
                return CustomResponse(False, 'Item is already approved.', 400)
            
            item.status = 'approved'
            item.save()

            #check if any item is declined
            if any(i.status == 'declined' and i.status != 'pending' for i in items):
                re.status = 'declined'
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
            
             # Check if all items are approved
            elif all(i.status == 'approved' for i in items):
                re.status = 'approved'
                re.area_manager = request.user
                re.area_manager_approved_at = timezone.now()
        
        elif request.user.role.name == "Internal Control":
            if item.internal_control_status == 'approved':
                return CustomResponse(False, 'Item is already approved.', 400)

            item.internal_control_status = 'approved'
            item.save()
            
            if any(i.internal_control_status == 'declined' and i.internal_control_status != 'pending' for i in items):
                re.internal_control_status = "declined"
                re.status = "pending"  # IC decline → send back as pending
                item.status = 'pending'
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()
            
            elif all(i.internal_control_status == 'approved' for i in items):
                re.internal_control_status = "approved"
                re.internal_control = request.user
                re.internal_control_approved_at = timezone.now()
        re.save()

        return CustomResponse(True,
            {
                'status': re.status,
                'internal_control_status': re.internal_control_status,
                'item_id': item.id
            },
            200
        )
        
        
class DeclineReimbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk):
        re = get_object_or_404(Reimbursement, pk=pk)
        items = re.items.all()
        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)

        if request.user.role.name == "Internal Control":
            re.internal_control_status = "declined"
            # Send back to Area Manager as pending
            re.status = "pending"
            items.update(status="pending") # Reset all items to pending
            re.internal_control = request.user
            re.internal_control_declined_at = timezone.now()
            
            # Update all items status to declined
            re.items.update(internal_control_status="declined")
            
        elif request.user.role.name == "Area Manager":
            # Final decline
            re.status = "declined"
            re.area_manager = request.user
            re.area_manager_declined_at = timezone.now()
            # Update all items status to declined
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
            {"status": re.status, "comment": comment_text, "internal_control_status": re.internal_control_status},
            200
        )


class DeclineReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)
        items = re.items.all()

        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)
        
        if request.user.role.name == "Area Manager":
            if item.status == 'declined':
                return CustomResponse(False, "Item is already declined", 400)
            
            # Decline this item
            item.status = 'declined'
            item.save()
            
            if any(i.status == 'pending' for i in items):
            # Some items still pending → request remains pending
                re.status = "pending"
            elif all(i.status != 'pending' for i in items):
            # No more pending items
                re.status = "declined"
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
            
        elif request.user.role.name == "Internal Control":
            if item.internal_control_status == 'declined':
                return CustomResponse(False, "Item is already declined", 400)
            
            # Decline this item
            item.internal_control_status = "declined"
            item.save()
            
            if any(i.internal_control_status == 'pending' for i in items):
                # Some items still pending → request remains pending
                re.internal_control_status = "pending"
                
            elif all(i.internal_control_status != 'pending' for i in items):
                # IC decline → send back as pending
                re.status = "pending"
                re.internal_control_status = "declined"
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()    
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
                "internal_control_status": re.internal_control_status,
                "item_id": item.id,
                "comment": comment_text
            },
            200
        )
        