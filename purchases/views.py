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

class PurchaseRequestView(APIView):
    """
    Handles listing and creating purchase requests
    """
    serializer_class = PurchaseRequestSerializer
    # authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, SubmitPurchaseRequest]

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
        return Response(serializer.data)

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
                return Response(
                    {"error": "Purchase requests required only for amounts ≥ ₦5,000"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Save the request
            purchase_request = serializer.save(
                requester=request.user,
                total_amount=total_amount
            )

            # Create items
            for item_data in request.data.get('items', []):
                PurchaseRequestItem.objects.create(
                    request=purchase_request,
                    gl_code=item_data['gl_code'],
                    expense_item=item_data['expense_item'],
                    unit_price=item_data['unit_price'],
                    quantity=item_data['quantity'],
                    total_price=item_data['unit_price'] * item_data['quantity']
                )

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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
        pr.save()

        # TODO: Send notification to requester
        return Response(
            {
                'status': 'approved',
                'voucher_id': f"PV-{pr.id}-{pr.created_at.strftime('%Y-%m-%d')}"
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
        pr.save()

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

