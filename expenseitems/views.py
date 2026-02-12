from django.shortcuts import render
from rest_framework.views import APIView
from utils.permissions import IsSuperUserOrReadOnly
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from users.auth import JWTAuthenticationFromCookie
from django.shortcuts import get_object_or_404
from helpers.response import CustomResponse
from helpers.exceptions import CustomValidationException
from .models import ExpenseItem
from .serializers import ItemSerializer
from utils.pagination import DynamicPageSizePagination
from rest_framework.exceptions import ValidationError
from services.byd import api as byd
# Create your views here.

class ExpenseItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]
    
    def get(self, request):
        try:
            param = self.request.query_params.get("paginated", 0)
            items = ExpenseItem.objects.all().order_by('-created_at')
            if param and param not in ["true", "false"]:
                raise ValidationError("Invalid query param. value must be either 'true' or 'false'")
            
            #Search query
            search_query = request.query_params.get('search', None)
            if search_query:
                items = items.filter(name__icontains=search_query)
            
            #Pginate results
            if not param or param == 'true':
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
            else:
                print("items", items)
                all_items = ItemSerializer(items, many=True).data
                print("items", items)
                return CustomResponse(
                    True,
                    "Items retrieved Successfully",
                    200,
                    all_items
                )
        except Exception as err:
            return CustomResponse(
                False,
                "Unable to retrieve expense items",
                400,
                {
                    "error":str(err)
                }
            )

        
    
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
    

class ListExpenseItemsView(APIView):
    """Get the list of expense Items from BYD."""
    def get(self, request):
        try:
            page=request.query_params.get("page")
            size=request.query_params.get("size")
            search=request.query_params.get("search")
            expense_items = byd.get_expense_items(page=page, size=size, search=search)
            return CustomResponse(
                valid=True,
                msg="Expense Items retrieved successfully", 
                status=200, data=expense_items)
        except Exception as err:
            return CustomResponse(
                valid=False,
                msg="Unable to retrieve expense items",
                status=400,
                data={
                    "error":str(err)
                }
            )
        

        
        
    
