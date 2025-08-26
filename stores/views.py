from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Region, Store
from .serializers import *
from django.contrib.auth import get_user_model
from helpers.response import CustomResponse
from django.shortcuts import get_object_or_404
from users.auth import JWTAuthenticationFromCookie
from utils.permissions import ManageUsers
from rest_framework.permissions import IsAuthenticated
from decimal import Decimal

User = get_user_model()


class StoreListView(APIView):
    serializer_class = StoreSerializer()
    """
    API endpoint for retrieving all stores.
    
    Returns:
    - List of all stores with their IDs, names, codes, and associated region
    - Used to populate the store dropdown in UI
    """
    def get(self, request):
        """
        Handles GET requests for store listing.
        """
        stores = Store.objects.all()
        serializer = StoreSerializer(stores, many=True)
        return CustomResponse(True, "Stores returned Successfully", data=serializer.data)
    
    


class RegionListView(APIView):
    serializer_class = RegionSerializer()
    """
    API endpoint for retrieving all regions.
    
    Returns:
    - List of all regions with their IDs and names
    - Used to populate the region dropdown in UI
    """
    def get(self, request):
        """
        Handles GET requests for region listing.
        
        """
        regions = Region.objects.all()
        serializer = RegionSerializer(regions, many=True)
        return CustomResponse(True, "Regions returned Successfully", data=serializer.data)
    
    def post(self, request):
        """Creates a new region"""
        serializer = RegionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "Region Added", data=serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StoreByRegionView(APIView):
    serializer_class = StoreRegionSerializer()
    """
    API endpoint for retrieving stores filtered by region.
    
    Used when:
    - User selects a region in UI
    - System needs to display stores for that specific region
    """
    def get(self, request, region_id):
        """
        Handles GET requests for store listing by region.
        
        Parameters:
        - region_id: ID of the selected region
        """
        # Only return active stores belonging to the specified region
        region = get_object_or_404(Region, id=region_id)
        serializer = StoreRegionSerializer(region)
        return CustomResponse(True, "Store returned according to selected region", data=serializer.data)

class AssignStoresToUserView(APIView):
    serializer_class = StoreSerializer()
    """
    API endpoint for assigning stores to users.
    
    Typical Flow:
    1. Admin selects stores in UI
    2. System sends store IDs to this endpoint
    3. Endpoint updates user's store assignments
    """
    def post(self, request, user_id):
        """
        Handles store assignment to a user.
        
        Parameters:
        - user_id: ID of the user being assigned stores
        - store_ids: List of store IDs to assign (in request body)
        """
        store_ids = request.data.get('store_ids', [])
        
        try:
            # Verify user exists
            user = User.objects.get(pk=user_id)
            
            # Get all valid stores from the provided IDs
            stores = Store.objects.filter(id__in=store_ids)
            
            # Replace existing assignments with new ones (atomic operation)
            #check if store alredy has area manager assigned
            if stores.filter(area_manager__isnull=False).exists():
                return Response(
                    {
                        "success": False,
                        "error": "Some of the selected stores already have an area manager assigned.",
                        "detail": "Please choose different stores."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.assigned_stores.set(stores)
            stores.update(area_manager=user)
            
            return Response(
                {
                    "success": True,
                    "message": "Stores assigned successfully",
                    "assigned_stores": [store.code for store in stores]  # Return store codes for confirmation
                },
                status=status.HTTP_200_OK
            )
            
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": "User not found",
                    "detail": f"No user exists with ID {user_id}"
                },
                status=status.HTTP_404_NOT_FOUND
            )
            
class ListAreaManagersByRegion(APIView):
    def get(self, request):
        regions = Region.objects.all()
        serializer = RegionAreaManagerSerializer(regions, many=True)
        return CustomResponse(True, "Regions and managers retrieved successfully", 200, serializer.data)
    

class StoreBudgetView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ManageUsers]
    
    def get(self, request):
        stores = Store.objects.all()
        serializer = StoreBudgetSerializer(stores, many=True)
        return CustomResponse(True, "Store Budgets Retrieved Successfully", 200, serializer.data)
    
    def post(self, request):
        """Creates a new store"""
        serializer = StoreBudgetSerializer(data=request.data)
        if serializer.is_valid():
            store = serializer.save()

            # Track initial budget history
            StoreBudgetHistory.objects.create(
                store=store,
                previous_budget=Decimal("0.00"),
                new_budget=store.budget,
                comment=request.data.get("comment", "Initial allocation"),
                updated_by=request.user if request.user.is_authenticated else None
            )

            # Initialize balance if budget > 0
            if store.balance == 0 and store.budget > 0:
                store.balance = store.budget
                store.save(update_fields=['balance'])

            return CustomResponse(True, "Store added", data=serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    def put(self, request, pk):
        store = get_object_or_404(Store, pk=pk)
        old_budget = store.budget

        serializer = StoreBudgetSerializer(store, data=request.data, partial=True)
        if serializer.is_valid():
            updated_store = serializer.save()

            # Track budget history if changed
            new_budget = updated_store.budget
            if old_budget != new_budget:
                StoreBudgetHistory.objects.create(
                    store=store,
                    previous_budget=old_budget,
                    new_budget=new_budget,
                    comment=request.data.get("comment"),
                    updated_by=request.user if request.user.is_authenticated else None
                )
                
            # Update balance if needed
            if store.balance == 0:
                store.balance = new_budget
                store.save(update_fields=['balance'])

            return CustomResponse(True, "Budget updated successfully", 200, serializer.data)

        return CustomResponse(False, serializer.errors, 400)
