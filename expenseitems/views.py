from django.shortcuts import render
from rest_framework.views import APIView
from utils.permissions import IsSuperUserOrReadOnly
from rest_framework.permissions import IsAuthenticated
from users.auth import JWTAuthenticationFromCookie
from django.shortcuts import get_object_or_404
from helpers.response import CustomResponse
from helpers.exceptions import CustomValidationException
from .models import ExpenseItem
from .serializers import ItemSerializer
from utils.pagination import DynamicPageSizePagination
# Create your views here.

class ExpenseItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]
    
    def get(self, request):
        items = ExpenseItem.objects.all().order_by('-created_at')
        
        #Search query
        search_query = request.query_params.get('search', None)
        if search_query:
            items = items.filter(name__icontains=search_query)
        
        #Pginate results
        paginator = DynamicPageSizePagination()
        
        items = paginator.paginate_queryset(items, request)
        serializer = ItemSerializer(items, many=True)
        return CustomResponse(True, 
                              "Items Retrieved Successfully", 
                              200,
                              {
                               "count": paginator.page.paginator.count,
                               "num_pages": paginator.page.paginator.num_pages,
                               "current_page": paginator.page.number,
                               "next": paginator.get_next_link(),
                               "previous": paginator.get_previous_link(),
                               "results": serializer.data,
                              })
    
    
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
    
    def delete(self, request, pk):
        """Deletes an Expense Item"""
        item = get_object_or_404(ExpenseItem, pk=pk)
        item.delete()
        return CustomResponse(True, "Item Deleted Successfully", 200)

        

        
        
    
