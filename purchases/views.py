from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import PurchaseRequestSerializer
from utils.permissions import *
from users.auth import JWTAuthenticationFromCookie
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from helpers.response import CustomResponse
from datetime import datetime
from django.db.models import Count
from rest_framework.pagination import PageNumberPagination

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
        queryset = PurchaseRequest.objects.all()

        # Restaurant Managers only see their own requests
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        # Area Managers see requests from their stores
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__region__area_manager=user)
            
    
        # Get status counts from full queryset (before pagination)
        status_counts = queryset.values('status').annotate(count=Count('id'))
        status_count_dict = {entry['status']: entry['count'] for entry in status_counts}

        # Paginate the queryset
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,
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
        Update an existing purchase request
        """
        pr = get_object_or_404(PurchaseRequest, pk=pk)


        serializer = PurchaseRequestSerializer(pr, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, serializer.data, 200)
        return CustomResponse(False, serializer.errors, 400)
    
    
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
        purchase_request.updated_by = request.user
        purchase_request.status = 'approved'
        purchase_request.voucher_id = f"PV-000{purchase_request.id}-{purchase_request.created_at.strftime('%Y-%m-%d')}"
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
            pr.save(user=request.user)
            
         # Check if all items are approved
        elif all(i.status == 'approved' for i in items):
            pr.status = 'approved'
            pr.voucher_id = f"PV-000{pr.id}-{pr.created_at.strftime('%Y-%m-%d')}"
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
        pr.save(user=request.user)
        
       

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
            pr.save(user=request.user)

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

    @extend_schema(
        summary="Search purchase requests",
    )
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

        # Get status counts from full queryset (before pagination)
        status_counts = queryset.values('status').annotate(count=Count('id'))
        status_count_dict = {entry['status']: entry['count'] for entry in status_counts}

        # Paginate the queryset
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Serialize paginated data
        serializer = PurchaseRequestSerializer(paginated_queryset, many=True)

        # Build custom response data
        response_data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "status_counts": status_count_dict,
        }

        return CustomResponse(True, "Filtered purchase requests retrieved", 200, response_data)


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

        # Get status counts (from full, unpaginated queryset)
        status_counts = queryset.values('status').annotate(count=Count('id'))
        status_count_dict = {entry['status']: entry['count'] for entry in status_counts}

        # Paginate the queryset
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

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