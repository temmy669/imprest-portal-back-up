# stores/serializers.py
from rest_framework import serializers
from .models import Region, Store

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']

class StoreSerializer(serializers.ModelSerializer):

    class Meta:
        model = Store
        fields = ['id','name', 'code',]
        
class StoreRegionSerializer(serializers.ModelSerializer):
    stores = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'stores']

    def get_stores(self, obj):
        stores = obj.region_stores.filter(is_active=True)
        return StoreSerializer(stores, many=True).data
    

class RegionAreaManagerSerializer(serializers.ModelSerializer):
    managers = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ['id', 'name', 'managers']

    def get_managers(self, obj):
        # get all area managers in this region
        managers = obj.user_region.filter(role__name="Area Manager", is_active=True)

        return [
            {
                "id": manager.id,
                "name": f"{manager.first_name} {manager.last_name}".strip(),
                "email": manager.email,
                "phone_number": manager.phone_number,
            }
            for manager in managers
        ]
