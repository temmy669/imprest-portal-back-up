from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from utils.permissions import *
from .models import Bank, Account
from .serializers import BankSerializer, AccountSerializer
from helpers.response import CustomResponse
from users.auth import JWTAuthenticationFromCookie
from utils.pagination import DynamicPageSizePagination

class BankView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]
    serializer_class = BankSerializer
    
    def get(self, request):
        banks = Bank.objects.all()
        #search banks
        search_query = request.query_params.get('search', None)
        if search_query:
            banks = banks.filter(name__icontains=search_query)
            
        #paginate results
        paginator = DynamicPageSizePagination()
        banks = paginator.paginate_queryset(banks, request)
            
        serializer = BankSerializer(banks, many=True)
        return CustomResponse(True, "banks returned successfully", 200, serializer.data)
    
    def post(self, request):
        
        serializer = BankSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "banks created successfully", 201, serializer.data)
        return CustomResponse(False, serializer.errors, 400)

class AccountView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]
    serializer_class = AccountSerializer
    
    def get(self, request):
        accounts = Account.objects.all()
        serializer = AccountSerializer(accounts, many=True)
        return CustomResponse(True, "Accounts returned successfully", 200, serializer.data)
    
    def post(self, request):

        serializer = AccountSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "Accounts created successfully", 201, serializer.data)
        return CustomResponse(False, serializer.errors, 400)

class AccountListByBankView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DisburseReimbursementRequest]

    def get(self, request, bank_id):
        accounts = Account.objects.filter(bank_id=bank_id)
        serializer = AccountSerializer(accounts, many=True)
        return CustomResponse(True, "success", 200, serializer.data)
