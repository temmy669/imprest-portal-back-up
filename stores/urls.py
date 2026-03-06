from django.urls import path
from .views import (
    StoreByRegionView, 
    RegionListView,
    DelistStoresFromUserView,
    AssignStoresToUserView, 
    StoreListView, 
    ListAreaManagersByRegion, 
    StoreBudgetView,
    StoreListFromSAPView)

urlpatterns = [
    path('regions', RegionListView.as_view(), name='list-regions'),
    path('regions/<int:pk>/', RegionListView.as_view(), name='region-detail'),
    path('region/<int:region_id>/', StoreByRegionView.as_view(), name= 'stores-by-region'),
    path('assign-stores/<int:user_id>/', AssignStoresToUserView.as_view(), name='assign-store'),
    path('delist-stores/<int:user_id>/', DelistStoresFromUserView.as_view(), name='delist-store'),
    path('manager-region/', ListAreaManagersByRegion.as_view(), name='manager-region'),
    path('store-budgets/', StoreBudgetView.as_view(), name='store-budget'),
    path('update-budget/<int:pk>/', StoreBudgetView.as_view(), name='update-budget'),
    path('add-store/', StoreBudgetView.as_view(), name='add-store'),
    path('', StoreListView.as_view(), name='store-list'),
    path('sap-stores-list/', StoreListFromSAPView.as_view(), name='sap-store-list'),
]