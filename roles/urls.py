from django.urls import path
from .views import RoleListView, PermissionListView

urlpatterns=[
    path('', RoleListView.as_view(), name= 'role-list'),
    path('permissions/', PermissionListView.as_view(), name='permission-list'),
]