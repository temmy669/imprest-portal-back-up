from django.shortcuts import render
from rest_framework.views import APIView
from utils.permissions import ManageUsers
from rest_framework.permissions import IsAuthenticated
from users.auth import JWTAuthenticationFromCookie
from django.shortcuts import get_object_or_404
from helpers.response import CustomResponse
from helpers.exceptions import CustomValidationException
from .models import ExpenseItem
from .serializers import ItemSerializer
# Create your views here.

class ExpenseItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ManageUsers]
    
    def get(self, request):
        items = ExpenseItem.objects.all()
        serializer = ItemSerializer(items, many=True)
        return CustomResponse(True, "Items Retrieved Successfully", 200, serializer.data)
    
    
    def post(self, request):
        """Creates a new Expense Item"""
        serializer = ItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "Item Added", 201, data=serializer.data)
        return CustomValidationException(serializer.errors, 400)
    
    
    def put(self, request, pk):
        """Updates Expense Item"""
        
        item = get_object_or_404(ExpenseItem, pk=pk)
        serializer = ItemSerializer(item, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_item = serializer.save()
            
            return CustomResponse(True, f"item updated successfully", 200, serializer.data)

        return CustomResponse(False, serializer.errors, 400)

        
        
        
        
    
