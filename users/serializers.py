from rest_framework import serializers
from .models import User
from stores.models import Store
from roles.serializers import RoleSerializer
from stores.serializers import StoreSerializer

class UserSerializer(serializers.ModelSerializer):
    assigned_stores = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Store.objects.all()
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'assigned_stores']
        
    def to_representation(self, instance):
        """Override to show nested objects instead of IDs for GET."""
        rep = super().to_representation(instance)
        rep['role'] = RoleSerializer(instance.role).data
        rep['assigned_stores'] = StoreSerializer(instance.assigned_stores.all(), many=True).data
        return rep  
    

    def create(self, validated_data):
        role = validated_data.get('role')
        user = super().create(validated_data)

        if role and role.name == 'Admin':
            user.is_superuser = True
        else:
            user.is_superuser = False

        user.save()
        return user
    
    def update(self, instance, validated_data):
        # Update basic fields
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.role = validated_data.get('role', instance.role)

        # Update M2M
        if 'assigned_stores' in validated_data:
            instance.assigned_stores.set(validated_data['assigned_stores'])

        # Optional: role-based superuser flag
        if instance.role and instance.role.name == 'Admin':
            instance.is_superuser = True
        else:
            instance.is_superuser = False

        instance.save()
        return instance

    