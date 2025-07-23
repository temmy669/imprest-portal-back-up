from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Region, Store
from .serializers import RegionSerializer, StoreSerializer, StoreRegionSerializer
from django.contrib.auth import get_user_model

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
        
        Response Format:
        [
            {
                "id": 1,
                "name": "Lagos Main",
                "code": "LMN001",
                "region": {"id": 1, "name": "South-South"}
            },
            ...
        ]
        """
        stores = Store.objects.all()
        serializer = StoreSerializer(stores, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Creates a new store"""
        serializer = StoreSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        
        Response Format:
        [
            {
                "id": 1,
                "name": "South-South"
            },
            ...
        ]
        """
        regions = Region.objects.all()
        serializer = RegionSerializer(regions, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Creates a new region"""
        serializer = RegionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
        
        Response Format:
        [
            {
                "id": 1,
                "name": "Lagos Main",
                "code": "LMN001",
                "region": {"id": 1, "name": "South-South"}
            },
            ...
        ]
        """
        # Only return active stores belonging to the specified region
        stores = Store.objects.filter(region_id=region_id, is_active=True)
        serializer = StoreRegionSerializer(stores, many=True)
        return Response(serializer.data)


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
        
        Request Body Format:
        {
            "store_ids": [1, 2, 3]
        }
        
        Responses:
        - 200: Success with confirmation message
        - 404: If user doesn't exist
        """
        store_ids = request.data.get('store_ids', [])
        
        try:
            # Verify user exists
            user = User.objects.get(pk=user_id)
            
            # Get all valid stores from the provided IDs
            stores = Store.objects.filter(id__in=store_ids)
            
            # Replace existing assignments with new ones (atomic operation)
            user.assigned_stores.set(stores)
            
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