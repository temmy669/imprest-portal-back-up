from django.shortcuts import render
from .models import Role
from rest_framework.views import APIView
from .serializers import RoleSerializer
from rest_framework.response import Response
from rest_framework import status

# Create your views here.
class RoleListView(APIView):
    serializer_class = RoleSerializer()
    def get(self, request):
        """
        Returns a list of all system roles
        Example response:
        {
            "roles": [
                {"id": 1, "name": "Restaurant Manager"},
                {"id": 2, "name": "Area Manager"}
            ]
        }
        """
        roles = Role.objects.all()
        serializer = RoleSerializer(roles, many=True)
        return Response({"roles": serializer.data})
    
    def post(self,request):
        """
        Creates a new role on the system
        Example request:
        {
            "name": "New Role Name"
        }
        
        """
        serializer = RoleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class PermissionListView(APIView):
    """
    Placeholder for future permission-related views.
    Currently not implemented.
    """
    def get(self, request):
        return Response({"message": "Permission management not implemented yet."}, status=status.HTTP_501_NOT_IMPLEMENTED)
    
    def post(self, request):
        return Response({"message": "Permission management not implemented yet."}, status=status.HTTP_501_NOT_IMPLEMENTED)

        