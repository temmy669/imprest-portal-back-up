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
from rest_framework.pagination import PageNumberPagination
from collections import Counter
import openpyxl
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from collections import Counter
from datetime import datetime

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
        queryset = PurchaseRequest.objects.all()

        # Restaurant Managers only see their own requests
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        # Area Managers see requests from their stores
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__region=user.region)
            
    
       # Paginate the queryset
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Calculate status counts for just this page
        status_list = [obj.status for obj in (paginated_queryset or [])]
        status_count_dict = dict(Counter(status_list))

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,  # total count (all pages)
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "status_counts": status_count_dict,       # counts only for current page
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


        serializer = PurchaseRequestSerializer(pr, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, serializer.data, 200)
        return CustomResponse(False, serializer.errors, 400)

class UpdatePurchaseRequestLimit(APIView):
    
    """Updates the minimum limit for items in a purchase request"""
    
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ManageUsers]
    
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
    

class ListApprovedPurchaseRequestView(APIView):
    """
    List all approved purchase requests for the current user.
    """
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewPurchaseRequest]

    @extend_schema(summary="List approved purchase requests")
    def get(self, request):
        queryset = PurchaseRequest.objects.filter(status='approved', requester=request.user)
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
        purchase_request = get_object_or_404(PurchaseRequest, pk=pk)

        # Object-level permission check
        self.check_object_permissions(request, purchase_request)
        
        if purchase_request.status == 'approved':
            return CustomResponse(False, 'Item is already approved.', 400)

        # Approve the request
        purchase_request.status = 'approved'
        purchase_request.voucher_id = f"PV-000{purchase_request.id}-{purchase_request.created_at.strftime('%Y-%m-%d')}"
        purchase_request.area_manager = request.user
        purchase_request.area_manager_approved_at = timezone.now()
        purchase_request.save()
        
        purchase_request_items = purchase_request.items.all()

        # Approve all related items
        purchase_request_items.update(status='approved')

        return CustomResponse(True,{
            "message": "Purchase request and items approved successfully.",
            "voucher_id": purchase_request.voucher_id
        }, 200)


        
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

        if item.status == 'approved':
            return CustomResponse(False, 'Item is already approved.', 400)

        item.status = 'approved'
        item.save()

        items = pr.items.all()


        # Check if any item is declined
        if any(i.status == 'declined' for i in items):
            pr.status = 'declined'
            pr.area_manager = request.user
            pr.area_manager_declined_at = timezone.now()
            pr.save(user=request.user)
            
         # Check if all items are approved
        elif all(i.status == 'approved' for i in items):
            pr.status = 'approved'
            pr.voucher_id = f"PV-000{pr.id}-{pr.created_at.strftime('%Y-%m-%d')}"
            pr.area_manager = request.user
            pr.area_manager_approved_at = timezone.now()
            pr.save(user=request.user)

        return CustomResponse(True,
            {
                'status': 'approved',
                'item_id': item.id
            },
            200
        )

        
class DeclinePurchaseRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclinePurchaseRequest]

    @extend_schema(
        summary="Decline purchase request",
        description="Declines request with mandatory comment",
    )
    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequest, pk=pk)

        # Object-level permission check
        self.check_object_permissions(request, pr)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False,
               'Comment is required when declining',
                400
            )

        pr.status = 'declined'
        pr.area_manager = request.user
        pr.area_manager_declined_at = timezone.now()
        pr.save()
        
        # Update all items to declined
        purchase_request_items = pr.items.all()
        purchase_request_items.update(status='approved')
        

        # Create decline comment
        Comment.objects.create(
            request=pr,
            user=request.user,
            text=comment_text
        )

        return CustomResponse(True,
            {
                'status': 'declined',
                'comment': comment_text
            },
            200
        )

class DeclinePurchaseRequestItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApprovePurchaseRequest]

    @extend_schema(
        summary="Decline purchase request item",
        description="Declines a specific item in a purchase request",
    )
    def post(self, request, pk, item_id):
        pr = get_object_or_404(PurchaseRequest, pk=pk)
        item = get_object_or_404(PurchaseRequestItem, pk=item_id, request=pr)

        self.check_object_permissions(request, pr)

        comment_text = request.data.get('comment', '').strip()
        
        if not comment_text:
            return CustomResponse(False,
                 'Comment is required when declining',
                400
            )

        if item.status == 'declined':
            return CustomResponse(False, "Item is already declined", 400)

        item.status = 'declined'
        item.save()
        
        items = pr.items.all()
        
        # Check if all items are still pending
        if any(item.status == 'pending' for item in  items):
            pr.status = 'pending'
        
        elif all(item.status != 'pending' for item in items):
            print("okay")
            pr.status = 'declined'
            pr.area_manager = request.user
            pr.area_manager_declined_at = timezone.now()
            pr.save()

        # Save comment (if supported)
        Comment.objects.create(
            request=pr,
            user=request.user,
            text=comment_text
        )

        return CustomResponse(True,
            {
                'status': 'declined',
                'item_id': item.id,
                'comment': comment_text
            },
            200
        )
        
        
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

        if search_query.upper().startswith("PR-"):
            try:
                request_id = int(search_query.upper().replace("PR-", ""))
                queryset = PurchaseRequest.objects.filter(id=request_id)
            except ValueError:
                return CustomResponse(False, "Invalid request ID format", 400)
        else:
            return CustomResponse(False, "Only PR-XXXX search is supported", 400)

        # Paginate queryset
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Status counts for paginated results only
        status_list = [obj.status for obj in (paginated_queryset or [])]
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
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Status counts for paginated results only
        status_list = [obj.status for obj in (paginated_queryset or [])]
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
