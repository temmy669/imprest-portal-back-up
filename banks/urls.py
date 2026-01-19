from django.urls import path
from .views import BankView, AccountView, AccountListByBankView, BankListView

urlpatterns = [
    path('', BankView.as_view(), name='bank-list'),
    path('list-banks/', BankListView.as_view(), name='bank-names-list'),
    path('accounts/', AccountView.as_view(), name='account-list'),
    path('<uuid:bank_id>/accounts/', AccountListByBankView.as_view(), name='account-list-by-bank'),
]