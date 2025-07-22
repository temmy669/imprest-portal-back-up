from django.urls import path
from .views import AzureLoginView, AzureCallbackView, AzureLogoutView, UserView

urlpatterns = [
    path('auth/login/', AzureLoginView.as_view(), name='azure-login'),
    path('auth/callback/', AzureCallbackView.as_view(), name='azure-callback'),
    path('auth/logout/', AzureLogoutView.as_view(), name='azure-logout'),
    path('users/', UserView.as_view(), name = 'user-list')
]
