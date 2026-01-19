# stores/serializers.py
from rest_framework import serializers
from .models import Region, Store, StoreBudgetHistory
from django.db.models import Sum
from decimal import Decimal

class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']

class StoreSerializer(serializers.ModelSerializer):

    class Meta:
        model = Store
        fields = ['id','name', 'code']
        
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
        
class StoreBudgetHistorySerializer(serializers.ModelSerializer):
    updated_by = serializers.SerializerMethodField()

    class Meta:
        model = StoreBudgetHistory
        fields = ['id', 'previous_budget', 'new_budget', 'comment', 'changed_at', 'updated_by']
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['changed_at'] = instance.changed_at.strftime('%d-%m-%Y')
        return rep

    def get_updated_by(self, obj):
        return f"{obj.updated_by.first_name} {obj.updated_by.last_name}" if obj.updated_by else None


class StoreBudgetSerializer(serializers.ModelSerializer):
    budget_history = StoreBudgetHistorySerializer(many=True, read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'code', 'name', 'region',
            'budget', 'balance', 'updated_at',
            'budget_history'
        ]
        read_only_fields = ['updated_at', 'created_at', 'balance']

    def get_balance(self, instance):
        approved_total = (
            instance.reimbursements
            .filter(internal_control_status='approved')
            .aggregate(total=Sum('total_amount'))
            ['total']
            or Decimal('0')
        )
        return str(instance.budget - approved_total)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['region'] = instance.region.name
        rep['updated_at'] = instance.updated_at.strftime('%d-%m-%Y')
        rep['created_at'] = instance.created_at.strftime('%d-%m-%Y')
        return rep