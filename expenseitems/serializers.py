from rest_framework import serializers
from .models import ExpenseItem

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model=ExpenseItem
        fields = ['id', 'name', 'gl_code', 'created_at']
        read_only_fields = ['created_at']
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['created_at'] = instance.created_at.strftime('%d-%m-%Y')
        
        return rep
        
        
        