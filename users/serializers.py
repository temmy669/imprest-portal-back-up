from rest_framework import serializers
from .models import User
from stores.models import Store, Region
from roles.models import Role
from stores.serializers import StoreSerializer, RegionSerializer
from django.db.models import Q

class UserSerializer(serializers.ModelSerializer):
    assigned_stores = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Store.objects.all(),
        required=False
    )
    store = serializers.PrimaryKeyRelatedField(
        queryset=Store.objects.all(),
        required=False
    )
    region = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'assigned_stores', 'store', 'region', 'is_active']
        read_only_fields = ['id', 'date_added', 'active_user_count', 'is_active']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['role'] = instance.role.name if instance.role else None
        rep['date_added'] = instance.created_at.strftime('%d-%m-%Y')

        if instance.region:
            rep['region'] = RegionSerializer(instance.region).data
        else:
            rep['region'] = None

        if instance.role and instance.role.name == 'Area Manager':
            rep['assigned_stores'] = StoreSerializer(instance.assigned_stores.all(), many=True).data
            rep.pop('store', None)
        else:
            rep['store'] = StoreSerializer(instance.store).data if instance.store else None
            rep.pop('assigned_stores', None)

        return rep
    
    def active_user_count(self, data):
        user = User.objects.filter(is_active=True).count()
        data['active_user_count'] = user
        return data
        

    def create(self, validated_data):
        role_data = validated_data.get('role')
        region = validated_data.pop('region', None)
    
        # If role is a dictionary (nested), get the ID
        if isinstance(role_data, dict):
            role_id = role_data.get('id')
            role = Role.objects.get(id=role_id) if role_id else None
        else:
            role = role_data  # Already a Role instance
    
        assigned_stores = validated_data.pop('assigned_stores', [])
        store = validated_data.pop('store', None)
        email = validated_data.get('email')
    
        if 'username' not in validated_data or not validated_data.get('username'):
            validated_data['username'] = email
    
        user = User(**validated_data)
        user.role = role
        user.region = region
        user.is_superuser = True if role and role.name == 'Admin' else False
        user.save()
    
        if role and role.name == 'Area Manager':
            user.assigned_stores.set(assigned_stores)
            user.store = None
        else:
            user.assigned_stores.clear()
            user.store = store
    
        user.save()
        return user



    def update(self, instance, validated_data):
        prev_role = instance.role.name if instance.role else None
    
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.role = validated_data.get('role', instance.role)
        instance.region = validated_data.get('region', instance.region)
    
        # Handle Area Manager assignment
        if 'assigned_stores' in validated_data and instance.role and instance.role.name == 'Area Manager':
            instance.assigned_stores.set(validated_data['assigned_stores'])
            instance.store = None
            #Add area manager to stores where assigned
            for store in instance.assigned_stores.all():
                store.area_manager = instance
                store.save()
        elif 'store' in validated_data:
            instance.store = validated_data['store']
            instance.assigned_stores.clear()
    
        instance.is_superuser = instance.role.name == 'Admin' if instance.role else False
    
        # If role is changed from Area Manager to something else
        if prev_role == 'Area Manager' and (not instance.role or instance.role.name != 'Area Manager'):
            # Find all stores where they are area manager
           stores_managed = Store.objects.filter(area_manager=instance)
    
        # Remove user as area manager from all those stores
        for store in stores_managed:
            store.area_manager = None
            store.save()
        
            instance.save()
        
        instance.assigned_stores.clear()
        return instance