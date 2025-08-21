from django.urls import path
from .views import StoreByRegionView, RegionListView, AssignStoresToUserView, StoreListView, ListAreaManagersByRegion, StoreBudgetView

urlpatterns = [
    path('regions', RegionListView.as_view(), name='list-regions'),
    path('region/<int:region_id>/', StoreByRegionView.as_view(), name= 'stores-by-region'),
    path('assign-stores/<int:user_id>/', AssignStoresToUserView.as_view(), name='assign-store'),
    path('manager-region/', ListAreaManagersByRegion.as_view(), name='manager-region'),
    path('store-budgets/', StoreBudgetView.as_view(), name='store-budget'),
    path('update-budget/<int:pk>/', StoreBudgetView.as_view(), name='update-budget'),
    path('', StoreListView.as_view(), name='store-list'),
]