from rest_framework import serializers
from .models import (
    Reimbursement,
    ReimbursementItem,
    ReimbursementComment
)
from purchases.models import LimitConfig
from decimal import Decimal
from utils.receipt_validation import validate_receipt

purchase_limit = LimitConfig.objects.first()
if purchase_limit is None:
    purchase_limit = LimitConfig(limit=5000)  # Default limit if not set


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
            'status', 'internal_control_status', 'receipt', 'requires_receipt', 'receipt_validated'
        ]
        read_only_fields = ['item_total', 'requires_receipt',]

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
        if item_name == 'transportation' and not self.partial:
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
        for field in ['unit_price', 'quantity', 'item_name', 'transportation_from', 'transportation_to', 'receipt', 'status']:
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
        read_only_fields = ['requester', 'disbursement_status']

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
            # REMOVE requester if present in validated_data
            validated_data.pop('requester', None)

            items_data = validated_data.pop('items')
            comments_data = validated_data.pop('comments', [])

            user = self.context['request'].user

            # Validate items
            invalid_items = [
                item for item in items_data
                if item.get('requires_receipt') and not item.get('receipt')
            ]
            if invalid_items:
                raise serializers.ValidationError({
                    "detail": "Some items require receipts before submission.",
                    "items_missing_receipts": [
                        {
                            "item_name": i.get('item_name'),
                            "unit_price": str(i.get('unit_price')),
                            "quantity": i.get('quantity'),
                        } for i in invalid_items
                    ]
                })

            total_amount = sum(
                Decimal(i['unit_price']) * i['quantity'] for i in items_data
            )

            reimbursement = Reimbursement.objects.create(
                requester=user,
                total_amount=total_amount,
                is_draft=False,
                **validated_data
            )

            # Create items
            for item in items_data:
                item['item_total'] = Decimal(item['unit_price']) * item['quantity']
                ReimbursementItem.objects.create(
                    reimbursement=reimbursement, **item
                )

            # Create comments
            for comment in comments_data:
                ReimbursementComment.objects.create(
                    reimbursement=reimbursement,
                    author=user,
                    **comment
                )

            return reimbursement

   
class ReimbursementUpdateSerializer(serializers.ModelSerializer):
    items = ReimbursementItemSerializer(many=True, required=False)
    comments = ReimbursementCommentSerializer(many=True, required=False)
    

    class Meta:
        model = Reimbursement
        fields = ['id', 'total_amount', 'items', 'comments']

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        comments_data = validated_data.pop('comments', None)

        updated_item_ids = []

        # Handle item updates and additions
        if items_data:
            initial_items = self.initial_data.get('items') or []

            for i, item_data in enumerate(items_data):
                item_id = initial_items[i].get('id') if i < len(initial_items) else None

                if item_id:
                    # Existing item
                    try:
                        item = instance.items.get(id=item_id)
                    except ReimbursementItem.DoesNotExist:
                        continue

                    # Detect changes
                    changed = any(
                        item_data.get(field) is not None and item_data[field] != getattr(item, field)
                        for field in ['unit_price', 'quantity', 'item_name', 'transportation_from', 'transportation_to', 'receipt']
                    )

                    if changed:
                        print(changed)
                        item_data['status'] = 'pending'
                        print(item_data['status'])

                    serializer = ReimbursementItemSerializer(item, data=item_data, partial=True)
                    serializer.is_valid(raise_exception=True)
                    updated_item = serializer.save()

                    if changed:
                        updated_item_ids.append(updated_item.id)

                else:
                    # NEW item
                    serializer = ReimbursementItemSerializer(data=item_data)
                    serializer.is_valid(raise_exception=True)
                    new_item = serializer.save(reimbursement=instance, status='pending')
                    updated_item_ids.append(new_item.id)

        # Recalculate total
        instance.total_amount = sum(item.item_total for item in instance.items.all())

        # Update reimbursement status — ONLY based on updated items
        if updated_item_ids:
            updated_items = instance.items.filter(id__in=updated_item_ids)
            if updated_items.filter(status='pending').exists():
                instance.status = 'pending'

        # Handle comments
        if comments_data:
            for comment in comments_data:
                ReimbursementComment.objects.create(
                    reimbursement=instance,
                    author=self.context['request'].user,
                    **comment
                )

        instance.save()
        return instance
