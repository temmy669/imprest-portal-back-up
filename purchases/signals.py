from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import PurchaseRequest
from utils.email_utils import send_approval_notification, send_rejection_notification

@receiver(pre_save, sender=PurchaseRequest)
def handle_purchase_request_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # Skip new instance creation

    try:
        old_instance = PurchaseRequest.objects.get(pk=instance.pk)
    except PurchaseRequest.DoesNotExist:
        return

    if old_instance.status != instance.status:
        if instance.status == 'approved':
            send_approval_notification(instance)
        elif instance.status == 'declined':
            send_rejection_notification(instance)
