from rest_framework import serializers
from .models import (
    Reimbursement, 
    ReimbursementItem, 
    ReimbursementComment
)
from decimal import Decimal


class ReimbursementCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementComment
        fields = ['id', 'text', 'author', 'created_at']
        read_only_fields = ['author', 'created_at']
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['author'] = f"{instance.author.first_name} {instance.author.last_name}"
        rep['created_at'] = instance.created_at.strftime('%d-%m-%Y %H:%M:%S')
        return rep

class ReimbursementItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementItem
        fields = [
            'id', 'item_name', 'gl_code', 'transportation_from', 'transportation_to',
            'unit_price', 'quantity', 'item_total', 'purchase_request_ref',
            'status', 'receipt', 'requires_receipt'
        ]
        read_only_fields = ['item_total', 'requires_receipt', 'status']
    
      
   
    def validate(self, attrs):
        unit_price = attrs.get('unit_price')
        quantity = attrs.get('quantity')
        item_name = attrs.get('item_name', '').strip().lower()
        purchase_request_ref = attrs.get('purchase_request_ref')
        receipt = attrs.get('receipt')

        # Basic validations
        if unit_price is not None and unit_price < 0:
            raise serializers.ValidationError({"unit_price": "Unit price cannot be negative."})
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError({"quantity": "Quantity must be greater than zero."})

        if item_name == 'transportation':
            if not attrs.get('transportation_from') or not attrs.get('transportation_to'):
                raise serializers.ValidationError(
                    "Transportation items must include 'transportation_from' and 'transportation_to'."
                )

        # ₦5,000 rule
        if unit_price is not None and quantity is not None:
            item_total = Decimal(unit_price) * quantity
            if item_total >= 5000:
                attrs['requires_receipt'] = True
                if not purchase_request_ref:
                    raise serializers.ValidationError(
                        f"Item '{attrs.get('item_name')}' total is above ₦5,000. Please raise a purchase request."
                    )
                elif Decimal(purchase_request_ref.split('-')[-1]) < item_total:
                    raise serializers.ValidationError(
                        f"Purchase request reference '{purchase_request_ref}' does not match item total ₦{item_total:,.2f}."
                    )  
        # Enforce receipt if purchase request exists
        if purchase_request_ref and not receipt:
            attrs['requires_receipt'] = True
            
        return attrs

    def create(self, validated_data):
        unit_price = validated_data.get('unit_price')
        quantity = validated_data.get('quantity')
        validated_data['item_total'] = Decimal(unit_price * quantity)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        for field in ['unit_price', 'quantity', 'item_name', 'transportation_from', 'transportation_to', 'receipt']:
            setattr(instance, field, validated_data.get(field, getattr(instance, field)))
        instance.item_total = Decimal(instance.unit_price) * instance.quantity
        instance.save()
        return instance


class ReimbursementSerializer(serializers.ModelSerializer):
    items = ReimbursementItemSerializer(many=True)
    comments = ReimbursementCommentSerializer(many=True, required=False)
    requester = serializers.StringRelatedField()

    class Meta:
        model = Reimbursement
        fields = ['id', 'status', 'is_draft', 'items', 'comments', 'requester', 'internal_control_status']
        read_only_fields = ['status', 'requester']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['store'] = instance.store.name if instance.store else None
        rep['store_code'] = instance.store.code
        rep['requester'] = f"{instance.requester.first_name} {instance.requester.last_name}"
        rep['requester_email'] = instance.requester.email
        rep['requester_phone'] = instance.requester.phone_number
        rep['request_date'] = instance.created_at.strftime('%d-%m-%Y')
        rep['request_id'] = f"RR-{instance.id:04d}"
        rep['role'] = instance.requester.role.name if instance.requester.role else None
        rep['total_amount'] = f"₦{instance.total_amount:,.2f}"
        

        if instance.area_manager_approved_at:
            rep['area_manager_approved_by'] = f"{instance.area_manager.first_name} {instance.area_manager.last_name}" if instance.area_manager else None
            rep['area_manager_approval_date'] = instance.area_manager_approved_at.strftime('%d-%m-%Y')

        if instance.internal_control_approved_at:
            rep['internal_control_approved_by'] = f"{instance.internal_control.first_name} {instance.internal_control.last_name}" if instance.internal_control else None
            rep['internal_control_approval_date'] = instance.internal_control_approved_at.strftime('%d-%m-%Y')

        return rep

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        comments_data = validated_data.pop('comments', [])
        user = self.context['request'].user
        validated_data['requester'] = user
        validated_data['store'] = user.store
        validated_data['total_amount'] = sum(
        Decimal(item['unit_price']) * item['quantity']
        for item in items_data
    )

        reimbursement = Reimbursement.objects.create(**validated_data)

        for item in items_data:
            item['item_total'] = Decimal(item['unit_price']) * item['quantity']
            ReimbursementItem.objects.create(reimbursement=reimbursement, **item)


        for comment in comments_data:
            ReimbursementComment.objects.create(
                reimbursement=reimbursement,
                author=self.context['request'].user,
                **comment
            )
    
        return reimbursement


class ReimbursementUpdateSerializer(serializers.ModelSerializer):
    items = ReimbursementItemSerializer(many=True, required=False)
    comments = ReimbursementCommentSerializer(many=True, required=False)

    class Meta:
        model = Reimbursement
        fields = ['items', 'comments']

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        comments_data = validated_data.pop('comments', None)

        if items_data:
            instance.items.all().delete()
            for item in items_data:
                ReimbursementItem.objects.create(reimbursement=instance, **item)

        if comments_data:
            for comment in comments_data:
                ReimbursementComment.objects.create(
                    reimbursement=instance,
                    author=self.context['request'].user,
                    **comment
                )

        instance.save()
        return instance
