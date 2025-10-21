from rest_framework import serializers
from .models import (
    Reimbursement, 
    ReimbursementItem, 
    ReimbursementComment
)
from purchases.models import LimitConfig
from decimal import Decimal

purchase_limit = LimitConfig.objects.first()


class ReimbursementCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementComment
        fields = ['id', 'text', 'author', 'created_at']
        read_only_fields = ['author', 'created_at', 'role']
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['author'] = f"{instance.author.first_name} {instance.author.last_name}"
        rep['created_at'] = instance.created_at.strftime('%d-%m-%Y %H:%M:%S')
        rep['role'] = instance.author.role.name if instance.author.role else None
        
        return rep

class ReimbursementItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReimbursementItem
        fields = [
            'id', 'item_name', 'gl_code', 'transportation_from', 'transportation_to',
            'unit_price', 'quantity', 'item_total', 'purchase_request_ref',
            'status', 'internal_control_status', 'receipt', 'requires_receipt'
        ]
        read_only_fields = ['item_total', 'requires_receipt', 'status', 'internal_control_status']

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


        # Transportation rule
        if item_name == 'transportation':
            if not attrs.get('transportation_from') or not attrs.get('transportation_to'):
                raise serializers.ValidationError(
                    "Transportation items must include 'transportation_from' and 'transportation_to'."
                )

        # ₦5,000 rule
        if unit_price is not None and quantity is not None:
            item_total = Decimal(unit_price) * quantity
            if item_total >= purchase_limit.limit:
                attrs['requires_receipt'] = True
                if not purchase_request_ref:
                    raise serializers.ValidationError(
                        f"Item '{attrs.get('item_name')}' total is above ₦5,000. Please raise a purchase request."
                    )

        # Enforce receipt if purchase request exists
        if purchase_request_ref:
            attrs['requires_receipt'] = True

        # Note: we do not fail here if receipt is missing — 
        # validation for that happens during "submission", not draft creation
        return attrs

    def create(self, validated_data):
        validated_data['item_total'] = Decimal(validated_data['unit_price']) * validated_data['quantity']
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
    requester = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Reimbursement
        fields = [
            'id', 'status', 'items', 'comments', 'requester',
            'internal_control_status', 'store', 'disbursement_status', 'bank', 'account'
        ]
        read_only_fields = ['status', 'requester', 'disbursement_status', 'internal_control_status']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['store'] = instance.store.name if instance.store else None
        rep['store_code'] = instance.store.code if instance.store else None
        rep['requester'] = f"{instance.requester.first_name} {instance.requester.last_name}"
        rep['requester_email'] = instance.requester.email
        rep['requester_phone'] = instance.requester.phone_number
        rep['request_date'] = instance.created_at.strftime('%d-%m-%Y')
        rep['request_id'] = f"RR-{instance.id:04d}"
        rep['role'] = instance.requester.role.name if instance.requester.role else None
        rep['total_amount'] = f"₦{instance.total_amount:,.2f}"
        rep['bank'] = instance.bank.bank_name if instance.bank else None
        rep['account'] = instance.account.account_name if instance.account else None
        rep['area_manager_approved_by'] = f"{instance.area_manager.first_name} {instance.area_manager.last_name}" if instance.area_manager else None
        rep['internal_control_approved_by'] = f"{instance.internal_control.first_name} {instance.internal_control.last_name}" if instance.internal_control else None
        rep['area_manager_approval_date'] = instance.area_manager_approved_at.strftime('%d-%m-%Y') if instance.area_manager_approved_at else None
        rep['internal_control_approval_date'] = instance.internal_control_approved_at.strftime('%d-%m-%Y') if instance.internal_control_approved_at else None
        
        return rep

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        comments_data = validated_data.pop('comments', [])
        user = self.context['request'].user

        total_amount = sum(Decimal(i['unit_price']) * i['quantity'] for i in items_data)
        reimbursement = Reimbursement(**validated_data)
        reimbursement.total_amount = total_amount
        reimbursement.is_draft = False
        reimbursement.save(user=user)
      

        for item in items_data:
            item['item_total'] = Decimal(item['unit_price']) * item['quantity']
            ReimbursementItem.objects.create(reimbursement=reimbursement, **item)

        for comment in comments_data:
            ReimbursementComment.objects.create(reimbursement=reimbursement, author=user, **comment)

        return reimbursement

    def validate_for_submission(self, reimbursement):
        """Custom validation called before submission"""
        missing_qs = reimbursement.items.filter(requires_receipt=True, receipt__isnull=True)
        if missing_qs.exists():
            raise serializers.ValidationError({
                "detail": "Some items require receipts before submission.",
                "items_missing_receipts": [
                    {"item_id": it.id, "item_name": it.item_name, "item_total": str(it.item_total)}
                    for it in missing_qs
                ],
            })


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
            total_amount = Decimal('0.00')
            for item_data in items_data:
                item_id = item_data.get('id')
                if item_id:
                    # Update existing item
                    item = ReimbursementItem.objects.get(id=item_id, reimbursement=instance)
                    for field in ['unit_price', 'quantity', 'item_name', 'transportation_from', 'transportation_to', 'receipt']:
                        setattr(item, field, item_data.get(field, getattr(item, field)))
                    item.item_total = Decimal(item.unit_price) * item.quantity
                    # If it was declined, set to pending
                    if item.status == 'declined':
                        item.status = 'pending'
                    item.save()
                    total_amount += item.item_total
                else:
                    # Create new item
                    item_total = Decimal(item_data['unit_price']) * item_data['quantity']
                    item_data['item_total'] = item_total
                    ReimbursementItem.objects.create(reimbursement=instance, **item_data)
                    total_amount += item_total
            instance.total_amount = total_amount
            # Check if any item is pending, set reimbursement to pending
            if instance.items.filter(status='pending').exists():
                instance.status = 'pending'
            instance.save()

        if comments_data:
            for comment in comments_data:
                ReimbursementComment.objects.create(
                    reimbursement=instance,
                    author=self.context['request'].user,
                    **comment
                )

        return instance
