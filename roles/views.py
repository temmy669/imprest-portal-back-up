from helpers.response import CustomResponse
from .models import Role, Permission
from rest_framework.views import APIView
from .serializers import RoleSerializer, PermissionSerializer

class RoleListView(APIView):
    serializer_class = RoleSerializer()
    def get(self, request):
        roles = Role.objects.all()
        serializer = RoleSerializer(roles, many=True)
        return CustomResponse(True, "Roles returned successfully", data=  serializer.data)
    
    def post(self,request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return CustomResponse(True, "Created", 201, serializer.data)

class PermissionListView(APIView):
    serializer_class = PermissionSerializer()
    """
    Placeholder for future permission-related views.
    Currently not implemented.
    """
    def get(self, request):
        permissions= Permission.objects.all()
        serializer = PermissionSerializer(permissions, many=True)
        return CustomResponse(True, data=serializer.data)
        
    def post(self, request):
        serializer = PermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return CustomResponse(True, "Created", 201, serializer.data)
   
    def put(self, request):
        # Update permission
        permission_id = request.data.get('id')
        Permission.objects.filter(id=permission_id).update(**request.data)
        return CustomResponse(True, "Permission updated successfully")
