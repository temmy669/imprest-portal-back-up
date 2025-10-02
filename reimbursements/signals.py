from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Reimbursement
# from utils.current_user import get_current_user
from utils.email_utils import send_reimbursement_approval_notification, send_reimbursement_rejection_notification, send_reimbursement_creation_notification

@receiver(post_save, sender=Reimbursement)
def handle_reimbursement_request_creation(sender, instance, created, **kwargs):
    if created:
        send_reimbursement_creation_notification(instance)

@receiver(pre_save, sender=Reimbursement)
def handle_reimbursement_request_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # Skip new instance creation

    try:
        old_instance = Reimbursement.objects.get(pk=instance.pk)
    except Reimbursement.DoesNotExist:
        return

    user = instance.updated_by
    role = getattr(getattr(user, "role", None), "name", "")

    # --- Area Manager updates status ---
    if role == "Area Manager" and old_instance.status != instance.status:
        if instance.status == "approved":
            send_reimbursement_approval_notification(instance, user)
        elif instance.status == "declined":
            latest_comment = instance.comments.order_by('-created_at').first()
            send_reimbursement_rejection_notification(instance, user, latest_comment)

    # --- Internal Control updates internal_control_status ---
    elif role == "Internal control person" and old_instance.internal_control_status != instance.internal_control_status:
        if instance.internal_control_status == "approved":
            send_reimbursement_approval_notification(instance, user)
        elif instance.internal_control_status == "declined":
            send_reimbursement_rejection_notification(instance ,user)

