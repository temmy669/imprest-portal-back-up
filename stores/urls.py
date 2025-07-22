from django.urls import path
from .views import StoreByRegionView, RegionListView, AssignStoresToUserView, StoreListView

urlpatterns = [
    path('regions', RegionListView.as_view(), name='list-regions'),
    path('region/<int:region_id>/', StoreByRegionView.as_view(), name= 'stores-by-region'),
    path('assign-stores/<int:user_id>/', AssignStoresToUserView.as_view(), name='assign-store'),
    path('', StoreListView.as_view(), name='store-list'),
]