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