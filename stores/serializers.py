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
        fields = ['name', 'code',]
        
class StoreRegionSerializer(serializers.ModelSerializer):
    stores = StoreSerializer(many=True, read_only=True)
    
    class Meta:
        model = Region
        fields = ['id', 'name', 'stores']