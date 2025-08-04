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
            

        serializer = PurchaseRequestSerializer(queryset, many=True)
        return CustomResponse(True, "Purchase Requests Returned Successfully", data = serializer.data)

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
        return CustomResponse(True, serializer.errors)
    
    def put(self, request, pk):
        """
        Update an existing purchase request
        """
        pr = get_object_or_404(PurchaseRequest, pk=pk)


        serializer = PurchaseRequestSerializer(pr, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
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

        # Approve the request
        purchase_request.updated_by = request.user
        purchase_request.status = 'approved'
        purchase_request.voucher_id = f"PV-000{purchase_request.id}-{purchase_request.created_at.strftime('%Y-%m-%d')}"
        purchase_request.save()
        
        purchase_request_items = purchase_request.items.all()

        # Approve all related items
        purchase_request_items.update(status='approved')

        return Response({
            "message": "Purchase request and items approved successfully.",
            "voucher_id": purchase_request.voucher_id
        }, status=status.HTTP_200_OK)


        
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
            return CustomResponse(True, 'Item is already approved.', 400)

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
            return CustomResponse(True,
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
            return CustomResponse(True,
                 'Comment is required when declining',
                400
            )

        if item.status == 'declined':
            return CustomResponse(True, "Item is already declined", 400)

        item.status = 'declined'
        item.save()
        
        items = pr.items.all()
        
        # Check if all items are still pending
        if any(item.status == 'pending' for item in  items):
            pr.status = 'pending'
              
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
