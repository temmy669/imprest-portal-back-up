from rest_framework import serializers
from .models import User
from stores.models import Store, Region
from roles.models import Role
from stores.serializers import StoreSerializer, RegionSerializer
from django.db.models import Q
from django.db import transaction

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


class UserUpdateSerializer(serializers.ModelSerializer):
    new_area_manager_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'region', 'store', 'assigned_stores', 'new_area_manager_id']
    
    def validate(self, data):
        """
        Validate at serializer level BEFORE update() is called
        """
        instance = self.instance
        prev_role = instance.role.name if instance.role else None
        new_role = data.get('role')
        new_role_name = new_role.name if new_role else prev_role
        
        # Check if changing FROM Area Manager to something else
        is_role_change_from_area_manager = (
            prev_role == 'Area Manager'
            and new_role_name != 'Area Manager'
        )
        
        if is_role_change_from_area_manager:
            # Check if there are stores that need reassignment
            has_assigned_stores = instance.assigned_stores.exists()
            new_area_manager_id = data.get('new_area_manager_id')
            
            if has_assigned_stores and not new_area_manager_id:
                stores_display = ", ".join(str(store) for store in instance.assigned_stores.all())
                raise serializers.ValidationError({
                    "new_area_manager_id": f"This Area Manager has assigned stores ({stores_display}). Please provide a new Area Manager ID to reassign them."
                })
            
            # Validate the new area manager exists and has correct role
            if new_area_manager_id:
                try:
                    new_area_manager = User.objects.get(id=new_area_manager_id)
                    if new_area_manager.role.name != 'Area Manager':
                        raise serializers.ValidationError({
                            "new_area_manager_id": f"User {new_area_manager.email} must have 'Area Manager' role."
                        })
                except User.DoesNotExist:
                    raise serializers.ValidationError({
                        "new_area_manager_id": "The specified Area Manager does not exist."
                    })
        
        return data

    def update(self, instance, validated_data):
        """
        Update user instance. Heavy validation is done in validate() method.
        """
        with transaction.atomic():
            # -----------------------------
            # 1. EXTRACT DATA
            # -----------------------------
            prev_role = instance.role.name if instance.role else None
            new_role = validated_data.get('role')
            new_role_name = new_role.name if new_role else prev_role
            new_area_manager_id = validated_data.pop('new_area_manager_id', None)
            
            is_role_change_from_area_manager = (
                prev_role == 'Area Manager'
                and new_role_name != 'Area Manager'
            )
            
            # -----------------------------
            # 2. VALIDATE INCOMING STORE ASSIGNMENTS
            # -----------------------------
            if 'assigned_stores' in validated_data and new_role_name == 'Area Manager':
                incoming_stores = validated_data['assigned_stores']
                incoming_store_ids = [s.id for s in incoming_stores]
                incoming_stores_qs = Store.objects.filter(id__in=incoming_store_ids)
                
                # Check for conflicts
                conflicting = incoming_stores_qs.filter(
                    area_manager__isnull=False
                ).exclude(area_manager=instance)
                
                if conflicting.exists():
                    conflicting_display = ", ".join(
                        f"{store} (assigned to {store.area_manager.name})" 
                        for store in conflicting
                    )
                    raise serializers.ValidationError({
                        "assigned_stores": f"Some stores already have an area manager: {conflicting_display}"
                    })
            
            # -----------------------------
            # 3. UPDATE BASIC FIELDS
            # -----------------------------
            instance.first_name = validated_data.get('first_name', instance.first_name)
            instance.last_name = validated_data.get('last_name', instance.last_name)
            instance.email = validated_data.get('email', instance.email)
            instance.role = new_role or instance.role
            instance.region = validated_data.get('region', instance.region)
            instance.is_superuser = instance.role.name == 'Admin' if instance.role else False
            
            # -----------------------------
            # 4. HANDLE STORE REASSIGNMENT (role change FROM Area Manager)
            # -----------------------------
            if is_role_change_from_area_manager:
                stores_to_reassign = list(instance.assigned_stores.all())
                
                if stores_to_reassign and new_area_manager_id:
                    # Get the new area manager (already validated in validate())
                    new_area_manager = User.objects.get(id=new_area_manager_id)
                    
                    # Transfer stores
                    Store.objects.filter(area_manager=instance).update(area_manager=new_area_manager)
                    new_area_manager.assigned_stores.add(*stores_to_reassign)
                    instance.assigned_stores.clear()
                
                # Clear store assignments for the demoted area manager
                instance.store = None
            
            # -----------------------------
            # 5. HANDLE STORE ASSIGNMENTS (for current/new Area Managers)
            # -----------------------------
            elif 'assigned_stores' in validated_data and new_role_name == 'Area Manager':
                incoming_store_ids = [s.id for s in validated_data['assigned_stores']]
                incoming_stores_qs = Store.objects.filter(id__in=incoming_store_ids)
                
                # Add new stores and update their area_manager field
                instance.assigned_stores.add(*incoming_stores_qs)
                incoming_stores_qs.update(area_manager=instance)
                instance.store = None
            
            # -----------------------------
            # 6. HANDLE SINGLE STORE ASSIGNMENT (for non-Area Manager roles)
            # -----------------------------
            elif 'store' in validated_data and new_role_name != 'Area Manager':
                instance.store = validated_data['store']
                # Clear any assigned_stores if switching to single store
                if instance.assigned_stores.exists():
                    Store.objects.filter(area_manager=instance).update(area_manager=None)
                    instance.assigned_stores.clear()
            
            # -----------------------------
            # 7. SAVE ONCE AT THE END
            # -----------------------------
            instance.save()
            
            return instance