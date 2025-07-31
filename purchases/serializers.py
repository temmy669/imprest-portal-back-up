from rest_framework import serializers
from .models import PurchaseRequest, PurchaseRequestItem, Comment


class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseRequestItem
        fields = ['id', 'gl_code', 'expense_item', 'unit_price', 'quantity', 'total_price']
        read_only_fields = ['total_price']

class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    
    class Meta:
        model = Comment
        fields = ['id', 'user', 'text', 'created_at']

class PurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True)
    requester = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'requester', 'store', 'status', 'status_display', 
            'total_amount', 'comment', 'items',
        ]
        read_only_fields = ['total_amount', 'requester_email', 'role', 'requester_phone', 'store_code', 'request_date', 'request_id', 'comments']
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['store'] = instance.store.name if instance.store else None
        rep['store_code'] = instance.store.code
        rep['requester'] = f"{instance.requester.first_name} {instance.requester.last_name}"
        rep['requester_email'] = instance .requester.email
        rep['requester_phone'] = instance.requester.phone_number
        rep['request_date'] = instance.created_at.strftime('%d-%m-%Y')
        rep['request_id'] = f"PR-{instance.id:04d}"
        rep['role'] = instance.requester.role.name if instance.requester.role else None
      
         
        return rep
    
    def validate(self, data):
        items = data.get('items', [])
        total = sum(item['unit_price'] * item['quantity'] for item in items)
        
        if total < 5000:  # N5,000 threshold from FRD
            raise serializers.ValidationError(
                "You do not require a purchase request for items below N5,000"
            )
        
        data['total_amount'] = total
        return data
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = PurchaseRequest.objects.create(**validated_data)
        
        for item_data in items_data:
            PurchaseRequestItem.objects.create(request=request, **item_data)
        
        return request