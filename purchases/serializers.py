from rest_framework import serializers
from .models import PurchaseRequest, PurchaseRequestItem, Comment, LimitConfig


purchase_limit = LimitConfig.objects.first()

class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseRequestItem
        fields = ['id', 'gl_code', 'expense_item', 'unit_price', 'quantity', 'total_price', 'status']
        read_only_fields = ['total_price']

class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    
    class Meta:
        model = Comment
        fields = ['id', 'user', 'text', 'created_at']
        read_only_fields = ['user', 'created_at', 'role']
        
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['user'] = f"{instance.user.first_name} {instance.user.last_name}"
        rep['created_at'] = instance.created_at.strftime('%d-%m-%Y %H:%M:%S')
        rep['role'] = instance.user.role.name if instance.user.role else None
        return rep

class PurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True)
    requester = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    comments = CommentSerializer(many=True, required=False)
    class Meta:
        model = PurchaseRequest
        fields = [
            'id', 'requester', 'store', 'status', 'status_display', 
            'total_amount', 'comments', 'items',
        ]
        read_only_fields = ['total_amount', 'requester_email', 'role', 'requester_phone', 'store_code', 'request_date', 'request_id', 'comments', 'voucher_id','approved_by', 'approval_date']
    
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
        rep['voucher'] = instance.voucher_id 
        
        #return approval details if status is approved
        if instance.status == "approved":
            rep['approved_by'] = f"{instance.area_manager.first_name} {instance.area_manager.last_name}" if instance.area_manager else None
            rep['approval_date'] = instance.area_manager_approved_at.strftime('%d-%m-%Y')
    
        return rep
        
    
    def validate(self, data):
        items = data.get('items', [])
        total = 0
       
        for item in items:
            item_total = item['unit_price'] * item['quantity']
            if item_total < purchase_limit.limit:
                raise serializers.ValidationError(
                    f"Item '{item['expense_item']}' total is below the purchase request limit and cannot be included in a purchase request."
                )
            total += item_total

        data['total_amount'] = total
        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        comments_data = validated_data.pop('comments', [])
        request = PurchaseRequest.objects.create(**validated_data)
        user = self.context['request'].user
    
        for item_data in items_data:
            PurchaseRequestItem.objects.create(request=request, **item_data)
    
        for comment_data in comments_data:
            Comment.objects.create(request=request, user=user, **comment_data)
    
        return request

class UpdatePurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True)
    comments = CommentSerializer(many=True, required=False)

    class Meta:
        model = PurchaseRequest
        fields = ['store', 'items', 'comments']

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        comments_data = validated_data.pop('comments', None)
        request_status_changed = False

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if items_data:
            for item_data in items_data:
                item_id = item_data.get('id')
                if item_id:
                    try:
                        item = PurchaseRequestItem.objects.get(id=item_id, request=instance)
                    except PurchaseRequestItem.DoesNotExist:
                        continue

                    for field in ['item_name', 'quantity', 'unit_price', 'reason']:
                        setattr(item, field, item_data.get(field, getattr(item, field)))

                    # Reset declined item to pending
                    if item.status == 'declined':
                        item.status = 'pending'
                        request_status_changed = True

                    item.save()

                else:
                    PurchaseRequestItem.objects.create(request=instance, **item_data)
                    request_status_changed = True

            if request_status_changed:
                instance.status = 'pending'
                instance.save()

        if comments_data:
            for comment in comments_data:
                Comment.objects.create(request=instance, user=self.context['request'].user, **comment)

        return instance

    
class LimitConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = LimitConfig
        fields = ['limit']
    
class ApprovedPurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True, read_only=True)

    """List serializer for approved purchase requests"""
    
    class Meta:
        model = PurchaseRequest
        fields = ['voucher_id', 'items', 'reimbursement']
        read_only_fields = ['voucher_id', 'request_name']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        
        # Only change request_name if approved
        if instance.status and instance.status.lower() == "approved":
            rep['request_name'] = f"PR-{instance.id:04d}-{instance.total_amount:.2f}"
        else:
            # Optional: keep original name or set it None
            rep['request_name'] = instance.request_name
        
        return rep
