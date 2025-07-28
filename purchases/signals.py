# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PurchaseRequest
from utils.email_utils import (
    send_approval_notification,
    send_rejection_notification,
)

@receiver(post_save, sender=PurchaseRequest)
def handle_purchase_request_status_change(sender, instance, created, **kwargs):
    if created:
        return  # Skip initial creation

    try:
        old_status = PurchaseRequest.objects.get(pk=instance.pk).status
    except PurchaseRequest.DoesNotExist:
        return

    new_status = instance.status

    if old_status != new_status:
        if new_status == 'approved':
            send_approval_notification(instance)
        elif new_status == 'declined':
            # Get the most recent comment as rejection reason
            last_comment = instance.comments.order_by('-created_at').first()
            reason = last_comment.text if last_comment else "No reason provided"
            send_rejection_notification(instance, reason)
