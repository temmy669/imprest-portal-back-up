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
            'status', 'internal_control_status', 'receipt', 'requires_receipt',
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
        items_data = validated_data.pop('items')
        comments_data = validated_data.pop('comments', [])
        user = self.context['request'].user

        # Validate items BEFORE saving anything
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

        # Compute total amount
        total_amount = sum(Decimal(i['unit_price']) * i['quantity'] for i in items_data)

        # Create reimbursement
        reimbursement = Reimbursement.objects.create(
            requester=user,
            total_amount=total_amount,
            is_draft=False,
            **validated_data
        )

        # Create items
        for item in items_data:
            item['item_total'] = Decimal(item['unit_price']) * item['quantity']
            ReimbursementItem.objects.create(reimbursement=reimbursement, **item)

        # Create comments
        for comment in comments_data:
            ReimbursementComment.objects.create(
                reimbursement=reimbursement, author=user, **comment
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

        # Handle item updates and additions
        if items_data:
            for i, item_data in enumerate(items_data):
                # Get the id from initial_data since it may not be in validated_data
                items = self.initial_data.get('items') or []
                item_id = (items[i].get('id') if i < len(items) and isinstance(items[i], dict) else None)
                
                if item_id:
                    try:
                        # Make sure the item belongs to this reimbursement
                        item = instance.items.get(id=item_id)
                        print(f"Updating item ID {item}")
                    except ReimbursementItem.DoesNotExist:
                        continue

                    # Use the nested serializer to update the item
                    item_serializer = ReimbursementItemSerializer(item, data=item_data, partial=True)
                    print(item_serializer)
                    if item_serializer.is_valid():
                        item_serializer.save(status='pending')

                else:
                    # Ensure required fields are present for creating a new item
                    if 'unit_price' not in item_data or 'quantity' not in item_data:
                        continue  # Skip if required fields are missing

                    # Check if an item with the same key attributes already exists to avoid duplicates
                    existing_item = instance.items.filter(
                        item_name=item_data.get('item_name'),
                        unit_price=item_data.get('unit_price'),
                        quantity=item_data.get('quantity')
                    ).first()

                    if existing_item:
                        # Update the existing item instead of creating a duplicate
                        item_serializer = ReimbursementItemSerializer(existing_item, data=item_data, partial=True)
                        if item_serializer.is_valid():
                            item_serializer.save(status='pending')
                    else:
                        # Create a new item using the nested serializer
                        item_serializer = ReimbursementItemSerializer(data=item_data)
                        if item_serializer.is_valid():
                            item_serializer.save(reimbursement=instance, status='pending')

        # After all updates, recalculate total for ALL items
        all_items = instance.items.all()
        instance.total_amount = sum(item.item_total for item in all_items)

        # Update reimbursement status based on all items
        item_statuses = list(all_items.values_list('status', flat=True))
        if any(status == 'pending' for status in item_statuses):
            instance.status = 'pending'
        elif all(status == 'approved' for status in item_statuses):
            instance.status = 'approved'
        else:
            instance.status = 'declined'

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
