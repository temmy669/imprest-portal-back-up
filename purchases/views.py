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
            queryset = queryset.filter(store__area_manager=user)
            

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

            # Check ₦5,000 threshold
            if total_amount < 5000:
                return CustomResponse( True, "Purchase requests required only for amounts ≥ ₦5,000")

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
        pr = get_object_or_404(PurchaseRequest, pk=pk)

        # Object-level permission check
        self.check_object_permissions(request, pr)

        pr.status = 'approved'
        pr.voucher_id = f"PV-000{pr.id}-{pr.created_at.strftime('%Y-%m-%d')}"
        pr.save()

        # TODO: Send notification to requester
        return Response(
            {
                'status': 'approved',
                'voucher_id': pr.voucher_id
            },
            status=status.HTTP_200_OK
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
            return Response(
                {'error': 'Comment is required when declining'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pr.status = 'declined'
        pr.save(user=request.user)

        # Create decline comment
        Comment.objects.create(
            request=pr,
            user=request.user,
            text=comment_text
        )

        # TODO: Send notification to requester with comment
        return Response(
            {
                'status': 'declined',
                'comment': comment_text
            },
            status=status.HTTP_200_OK
        )

