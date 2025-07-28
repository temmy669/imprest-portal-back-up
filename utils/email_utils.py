from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from users.models import User

def send_approval_notification(purchase_request):
    """
    Sends approval notification to requester with complete request details
    """
    requester = User.objects.get(id=purchase_request.requester_id)
    
    # Build context for email template
    context = {
        'request_id': f"PR-{purchase_request.id:04d}",
        'requester_name': requester.get_full_name(),
        'store_name': purchase_request.store.name,
        'total_amount': f"₦{purchase_request.total_amount:,.2f}",
        'items': purchase_request.items.all(),
        'approval_date': purchase_request.updated_at.strftime("%b %d, %Y %I:%M %p"),
        'status': purchase_request.get_status_display(),
        'voucher_id': getattr(purchase_request, 'voucher_id', 'Pending')
    }

    # Render HTML and plain text versions
    html_message = render_to_string('email_templates/approval.html', context)
    plain_message = strip_tags(html_message)
    
    # Send email
    send_mail(
        subject=f"Purchase Request Approved - {context['request_id']}",
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[requester.email],
        html_message=html_message,
        fail_silently=False
    )

def send_rejection_notification(purchase_request, comment):
    """
    Sends rejection notification with reason
    """
    requester = User.objects.get(id=purchase_request.requester_id)
    
    context = {
        'request_id': f"PR-{purchase_request.id:04d}",
        'rejector_name': purchase_request.updated_by.get_full_name(),
        'rejection_reason': comment,
        'items': purchase_request.items.all(),
        'rejection_date': purchase_request.updated_at.strftime("%b %d, %Y %I:%M %p")
    }

    html_message = render_to_string('emails/purchase_rejected.html', context)
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=f"Purchase Request Declined - {context['request_id']}",
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[requester.email],
        html_message=html_message
    )