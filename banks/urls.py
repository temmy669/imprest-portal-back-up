from django.urls import path
from .views import BankView, AccountView, AccountListByBankView

urlpatterns = [
    path('', BankView.as_view(), name='bank-list'),
    path('accounts/', AccountView.as_view(), name='account-list'),
    path('<uuid:bank_id>/accounts/', AccountListByBankView.as_view(), name='account-list-by-bank'),
]