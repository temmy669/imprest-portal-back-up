from rest_framework import serializers
from .models import User
from stores.models import Store

class UserSerializer(serializers.ModelSerializer):
    assigned_stores = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Store.objects.all()
    )

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'assigned_stores']
