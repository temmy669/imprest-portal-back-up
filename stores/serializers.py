# stores/serializers.py
from rest_framework import serializers
from .models import Region, Store

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']

class StoreSerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)
    region_id = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(),
        source='region',
        write_only=True
    )

    class Meta:
        model = Store
        fields = ['id', 'name', 'code', 'region', 'region_id']
        
class StoreRegionSerializer(serializers.ModelSerializer):
    stores = StoreSerializer(many=True, read_only=True)
    
    class Meta:
        model = Region
        fields = ['id', 'name', 'stores']