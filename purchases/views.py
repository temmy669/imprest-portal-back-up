from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import *
from utils.permissions import *
from users.auth import JWTAuthenticationFromCookie
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from helpers.response import CustomResponse
from datetime import datetime
from django.db.models import Count
from utils.pagination import DynamicPageSizePagination
from collections import Counter
import openpyxl
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from collections import Counter
from datetime import datetime
from django.db.models import Q
from utils.email_utils import send_rejection_notification, send_approval_notification
from django.db import transaction

class PurchaseRequestView(APIView):
    """
    Handles listing and creating purchase requests
    """
    serializer_class = PurchaseRequestSerializer
    authentication_classes = [JWTAuthenticationFromCookie]
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), ViewPurchaseRequest()]
        elif self.request.method == 'POST':
            return [IsAuthenticated(), SubmitPurchaseRequest()]
        elif self.request.method == 'PUT':
            return [IsAuthenticated(), ChangePurchaseRequest()]  # If you define it
        return [IsAuthenticated()]

    def get(self, request):
        """
        List purchase requests (filtered by user's role)
        """
        user = request.user
        print(user)
        queryset = PurchaseRequest.objects.all().order_by('-created_at')

        # Restaurant Managers only see their own requests
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
            
        # Area Managers see requests from their stores
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__in=user.assigned_stores.all())
            
        # Paginate the queryset
        paginator = DynamicPageSizePagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        
        # Calculate status counts
        status_list = [obj.status for obj in (queryset or [])]
            
        status = request.query_params.get("status")
        
        if status:
            queryset = queryset.filter(status__iexact=status)
            paginated_queryset = paginator.paginate_queryset(queryset, request)
            
    
        
        # print(status_list)
        status_count_dict = dict(Counter(status_list))
        
        #return empty status count if queryset is empty after filters
        if not queryset.exists():
            status_count_dict = {}
            

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,  # total count (all pages)
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "status_counts": status_count_dict,       
        }

        return CustomResponse(True, "Filtered purchase requests retrieved", 200, response_data)


    def post(self, request):
        """
        Create a new purchase request
        """
        serializer = PurchaseRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Calculate total amount
            total_amount = sum(
                item['unit_price'] * item['quantity']
                for item in request.data.get('items', [])
            )

            # Save the request
            purchase_request = serializer.save(
                requester=request.user,
                total_amount=total_amount
            )

            return CustomResponse(True, "Purchase Request Created Successfully", 201, serializer.data)
        return CustomResponse(False, serializer.errors)
    
    def put(self, request, pk):
        """
        Updates an existing purchase request
        """
        pr = get_object_or_404(PurchaseRequest, pk=pk)


        serializer = UpdatePurchaseRequestSerializer(pr, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "request updated successfully", 200, serializer.data)
        return CustomResponse(False, serializer.errors, 400)

class UpdatePurchaseRequestLimit(APIView):
    
    """Updates the minimum limit for items in a purchase request"""
    
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]
    
    def put(self, request):
        serializer = LimitConfigSerializer(data=request.data)
        if serializer.is_valid():
            limit_value = serializer.validated_data.get('limit')
            if limit_value is None:
                return CustomResponse(False, "'limit' field is required.", 400)
            config, created = LimitConfig.objects.get_or_create(id=1)
            config.limit = limit_value
            config.save()
            return CustomResponse(True, "Limit updated successfully", 200, {'limit': config.limit})
        return CustomResponse(False, serializer.errors, 400)
    
    def get(self, request):
        try:
            config = LimitConfig.objects.get(id=1)
            return CustomResponse(True, "Limit retrieved successfully", 200, {'limit': config.limit})
        except LimitConfig.DoesNotExist:
            return CustomResponse(False, "Limit configuration not found", 404)
    

class ListApprovedPurchaseRequestView(APIView):
    """
    List all approved purchase requests for the current user.
    """
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewPurchaseRequest]

    @extend_schema(summary="List approved purchase requests")
    def get(self, request):
        queryset = PurchaseRequest.objects.filter(
            status='approved', 
            requester=request.user
        ).filter(
            Q(reimbursement__isnull=True) | Q(reimbursement__status='pending')
            ).order_by('-created_at')
        serializer = ApprovedPurchaseRequestSerializer(queryset, many=True)

        return CustomResponse(True, "Approved purchase requests retrieved", 200, serializer.data)

    
class ApprovePurchaseRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApprovePurchaseRequest]

    @extend_schema(
        summary="Approve purchase request",
        description="Only Area Managers can approve requests for their stores",
    )
    def post(self, request, pk):

        with transaction.atomic():

            # Lock PR row
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)

            # Object-level permission check
            self.check_object_permissions(request, pr)

            if pr.status == "approved":
                return CustomResponse(False, "Request already approved.", 400)

            # Fetch and lock all related items
            items = list(pr.items.select_for_update())

            # ❌ If any item is declined → PR cannot be approved
            if any(item.status == "declined" for item in items):
                return CustomResponse(
                    False,
                    "Cannot approve request because one or more items are declined.",
                    400
                )

            # All items must become approved
            for item in items:
                item.status = "approved"
                item.save()

            # Approve the PR itself
            pr.status = "approved"
            pr.voucher_id = f"PV-{pr.id:04d}-{pr.created_at.strftime('%Y-%m-%d')}"
            pr.area_manager = request.user
            pr.area_manager_approved_at = timezone.now()
            pr.save()

        # Optionally trigger approval email (if you want)
        send_approval_notification(pr)

        return CustomResponse(
            True,
            {
                "message": "Purchase request and all items approved successfully.",
                "voucher_id": pr.voucher_id
            },
            200
        )

        
class ApprovePurchaseRequestItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApprovePurchaseRequest]

    @extend_schema(
        summary="Approve purchase request item",
        description="Approves a specific item in a purchase request",
    )
    def post(self, request, pk, item_id):
        pr = get_object_or_404(PurchaseRequest, pk=pk)
        item = get_object_or_404(PurchaseRequestItem, pk=item_id, request=pr)

        # Object-level permission check
        self.check_object_permissions(request, pr)

        if item.status == "approved":
            return CustomResponse(False, "Item is already approved.", 400)

        with transaction.atomic():

            # Lock PR and item row
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)
            item = PurchaseRequestItem.objects.select_for_update().get(pk=item_id, request=pr)

            # Approve this item
            item.status = "approved"
            item.save()

            # Re-fetch all items safely
            items = list(pr.items.select_for_update())

            # If ANY item is declined → PR remains declined
            if any(i.status == "declined" for i in items):
                pr.status = "declined"
                pr.area_manager = request.user
                pr.area_manager_declined_at = timezone.now()
                pr.save()
                
                # Decline emails are only sent when an item is DECLINED, not approved.

            # If ALL items are approved → PR is approved
            elif all(i.status == "approved" for i in items):
                pr.status = "approved"
                pr.voucher_id = f"PV-{pr.id:04d}-{pr.created_at.strftime('%Y-%m-%d')}"
                pr.area_manager = request.user
                pr.area_manager_approved_at = timezone.now()
                pr.save()
                send_approval_notification(pr)  # Uncomment when ready

            # Else: some pending, some approved → PR stays pending
            else:
                pr.status = "pending"
                pr.save()

        return CustomResponse(
            True,
            {
                "status": item.status,
                "item_id": item.id,
                "purchase_request_status": pr.status
            },
            200
        )

        
class DeclinePurchaseRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclinePurchaseRequest]

    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequest, pk=pk)
        self.check_object_permissions(request, pr)

        comment_text = request.data.get("comment", "").strip()
        if not comment_text:
            return CustomResponse(False, "Comment is required when declining.", 400)

        with transaction.atomic():
            # Lock the PR to prevent concurrency issues
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)

            if pr.status in ("approved", "declined"):
                return CustomResponse(False, "This purchase request has already been processed.", 400)

            # Update PR status
            pr.status = "declined"
            pr.area_manager = request.user
            pr.area_manager_declined_at = timezone.now()
            pr.save()

            # Decline all items
            pr.items.update(status="declined")

            # Create decline comment
            comment = Comment.objects.create(
                request=pr,
                user=request.user,
                text=comment_text
            )

        # Send notification AFTER the transaction commits
        send_rejection_notification(pr, comment)

        return CustomResponse(True, {
            "id": pr.id,
            "status": "declined",
            "comment": comment_text
        }, 200)

class DeclinePurchaseRequestItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclinePurchaseRequest]

    def post(self, request, pk, item_id):
        item = get_object_or_404(PurchaseRequestItem, pk=item_id, request_id=pk)
        pr = item.request
        self.check_object_permissions(request, pr)

        comment_text = request.data.get("comment", "").strip()
        if not comment_text:
            return CustomResponse(False, "Comment is required for item decline.", 400)

        with transaction.atomic():
            # Lock PR and items for concurrency safety
            pr = PurchaseRequest.objects.select_for_update().get(pk=pk)
            item = pr.items.select_for_update().get(pk=item_id)

            if pr.status in ("approved", "declined"):
                return CustomResponse(False, "This purchase request has already been processed.", 400)

            # Decline the single item
            item.status = "declined"
            item.save()

            # Create comment for this item
            comment = Comment.objects.create(
                request=pr,
                user=request.user,
                text=comment_text
            )

            # Determine if all items are now declined
            all_declined = not pr.items.exclude(status="declined").exists()

            if all_declined:
                pr.status = "declined"
                pr.area_manager = request.user
                pr.area_manager_declined_at = timezone.now()
                pr.save()

        # Send notification if PR became fully declined
        if all_declined:
            send_rejection_notification(pr, comment)

        return CustomResponse(True, {
            "item": item_id,
            "status": "declined",
            "comment": comment_text
        }, 200)
        
        
class SearchPurchaseRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewPurchaseRequest]

    @extend_schema(summary="Search purchase requests")
    def get(self, request):
        """
        Search purchase requests by request ID (e.g. 'PR-0027')
        """
        search_query = request.query_params.get('q', '').strip()
        if not search_query:
            return CustomResponse(False, "Search query is required", 400)

        queryset = PurchaseRequest.objects.none()
        
        
        # Paginate queryset
        paginator = DynamicPageSizePagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        if search_query.upper().startswith("PR-"):
            try:
                request_id = int(search_query.upper().replace("PR-", ""))
                queryset = PurchaseRequest.objects.filter(id=request_id)
                paginated_queryset = paginator.paginate_queryset(queryset, request)
            except ValueError:
                return CustomResponse(False, "Invalid request ID format", 400)
        else:
            return CustomResponse(False, "Only PR-XXXX search is supported", 400)


        # Status counts for paginated results only
        status_list = [obj.status for obj in (queryset or [])]
        status_count_dict = dict(Counter(status_list))

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "status_counts": status_count_dict
        }

        return CustomResponse(True, "Filtered purchase requests retrieved", 200, response_data)


from collections import Counter
from datetime import datetime

class DateRangeFilterView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewPurchaseRequest]

    def get(self, request):
        """
        Filter purchase requests by date range with pagination and status counts.
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            return CustomResponse(False, "Both start_date and end_date are required", 400)

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return CustomResponse(False, "Invalid date format. Use YYYY-MM-DD", 400)

        if start_date > end_date:
            return CustomResponse(False, "start_date cannot be after end_date", 400)

        # Base queryset
        queryset = PurchaseRequest.objects.filter(
            created_at__date__gte=start_date.date(),
            created_at__date__lte=end_date.date()
        )

        # Paginate queryset
        paginator = DynamicPageSizePagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Status counts for paginated results only
        status_list = [obj.status for obj in (queryset or [])]
        status_count_dict = dict(Counter(status_list))

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "status_counts": status_count_dict
        }

        return CustomResponse(True, "Filtered purchase requests retrieved", 200, response_data)

class ExportPurchaseRequest(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewPurchaseRequest]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status = request.query_params.get('status')
        user = request.user

        if not start_date or not end_date or not status:
            return CustomResponse(False, "start_date, end_date and status are required", 400)

        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return CustomResponse(False, "Invalid date format. Use YYYY-MM-DD", 400)

        if start_date > end_date:
            return CustomResponse(False, "start_date cannot be after end_date", 400)

        # Filter queryset
        queryset = PurchaseRequest.objects.filter(
            created_at__date__gte=start_date.date(),
            created_at__date__lte=end_date.date(),
            status__iexact=status
            
        )
        
        
        # Restaurant Managers only see their own requests
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        # Area Managers see requests from their stores
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__region=user.region)

        # Create workbook
        workbook = openpyxl.Workbook()
        sheet = workbook.active

        # Keep title <= 31 chars
        sheet.title = f"PRs {start_date:%d-%m} to {end_date:%d-%m}"

        # Define headers
        headers = ["Request ID", "Requester", "Store", "Total Amount", "Status", "Date Created"]
        sheet.append(headers)

        # Add rows
        for pr in queryset:
            row = [
                f"PR-{pr.id:04d}",
                f"{pr.requester.first_name} {pr.requester.last_name}",
                pr.store.name if pr.store else "",
                f"₦{pr.total_amount:,.2f}",
                pr.status.capitalize(),
                pr.created_at.strftime('%Y-%m-%d'),
            ]
            sheet.append(row)

        # Adjust column widths
        for col in sheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            sheet.column_dimensions[column].width = max_length + 2

        # Prepare response
        file_name = f"purchase_requests_{start_date.date()}_{end_date.date()}.xlsx"
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'

        workbook.save(response)  # Write workbook to response
        return response
