from django.urls import path
from .views import (
    AzureLoginView, AzureCallbackView, AzureLogoutView, DummyLogin, 
    UserView, MeView, SearchUserView, ToggleUserActivationView, UpdateUserView)

urlpatterns = [
    path('auth/login/', AzureLoginView.as_view(), name='azure-login'),
    path('auth/callback/', AzureCallbackView.as_view(), name='azure-callback'),
    path('auth/logout/', AzureLogoutView.as_view(), name='azure-logout'),
    path('users/', UserView.as_view(), name = 'user-list'),
    path('users/<int:pk>/', UserView.as_view(), name = 'user-detail'),
    path('users/<int:pk>/edit', UpdateUserView.as_view()),
    path("n0t-0k@y/", DummyLogin.as_view(), name="dummy-login"),
    path('auth/me/', MeView.as_view(), name='me'),
    path('user/search/', SearchUserView.as_view(), name= 'search-user'),
    path('user/<int:user_id>/deactivate/', ToggleUserActivationView.as_view(), name='deactivate-user'),
    
]
