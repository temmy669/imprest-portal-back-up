from rest_framework import serializers
from .models import User
from stores.models import Store
from roles.models import Role
from stores.serializers import StoreSerializer

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

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'assigned_stores', 'store']
        read_only_fields = ['id', 'date_added']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['role'] = instance.role.name if instance.role else None
        rep['date_added'] = instance.data_updated_at.strftime('%d-%m-%Y')

        if instance.role and instance.role.name == 'Area Manager':
            rep['assigned_stores'] = StoreSerializer(instance.assigned_stores.all(), many=True).data
            rep.pop('store', None)  # remove store field for area manager
        else:
            rep['store'] = StoreSerializer(instance.store).data if instance.store else None
            rep.pop('assigned_stores', None)  # remove assigned_stores field for non-area-manager roles

        return rep

    def create(self, validated_data):
        # Extract nested role data if needed
        role_data = validated_data.get('role')

        # If role is a dictionary (nested), get the ID
        if isinstance(role_data, dict):
            role_id = role_data.get('id')
            role = Role.objects.get(id=role_id) if role_id else None
        else:
            role = role_data  # Already a Role instance

        assigned_stores = validated_data.pop('assigned_stores', [])
        store = validated_data.pop('store', None)
        email = validated_data.get('email')

        user = User.objects.filter(email=email).first()

        if user:
            # Update the existing user
            for attr, value in validated_data.items():
                setattr(user, attr, value)
        else:
            user = User(**validated_data)

        user.role = role

        if role and role.name == 'Admin':
            user.is_superuser = True
        else:
            user.is_superuser = False

        user.save()  # Save before assigning M2M fields

        if role and role.name == 'Area Manager':
            user.assigned_stores.set(assigned_stores)
            user.store = None
        else:
            user.assigned_stores.clear()
            user.store = store

        user.save()
        return user



    def update(self, instance, validated_data):
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.role = validated_data.get('role', instance.role)

        if 'assigned_stores' in validated_data and instance.role.name == 'Area Manager':
            instance.assigned_stores.set(validated_data['assigned_stores'])
            instance.store = None
        elif 'store' in validated_data:
            instance.store = validated_data['store']
            instance.assigned_stores.clear()

        instance.is_superuser = instance.role.name == 'Admin' if instance.role else False

        instance.save()
        return instance
