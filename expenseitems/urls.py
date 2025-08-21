from django.urls import path
from .views import ExpenseItemView

urlpatterns = [
    path('expense-item/', ExpenseItemView.as_view(), name='expense-item'),
    path('expense-item/<int:pk>/', ExpenseItemView.as_view(), name='update-item')
]
