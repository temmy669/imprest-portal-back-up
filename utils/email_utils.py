from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.forms import model_to_dict
from django.utils.html import strip_tags
from users.models import User
from roles.models import Role
from purchases.models import Comment
import logging 

logger = logging.getLogger(__name__)

def send_approval_notification(purchase_request):
    """
    Sends approval notification to requester with complete request details
    """
    requester = purchase_request.requester
    # print(html_message)
   
    
    # Build context for email template
    context = {
        'request_id': f"PR-{purchase_request.id:04d}",
        'requester_name': requester.get_full_name(),
        'store_name': purchase_request.store.name,
        'store_code': purchase_request.store.code,
        'approvedby_name': purchase_request.area_manager.get_full_name(),
        'total_amount': f"₦{purchase_request.total_amount:,.2f}",
        'items': purchase_request.items.all(),
        'approval_date': purchase_request.area_manager_approved_at.strftime("%b %d, %Y %I:%M %p"),
        'status': purchase_request.get_status_display(),
        'voucher_id': getattr(purchase_request, 'voucher_id'),
        'request_date': purchase_request.created_at.strftime("%b %d, %Y %I:%M %p"),
        'company_name': settings.COMPANY_NAME
    }

    # Render HTML and plain text versions
    html_message = render_to_string('pr_approval.html', context)
    plain_message = strip_tags(html_message)
  
   
    # Send email
    send_mail(
        subject=f"Purchase Request Approved - {context['request_id']}",
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[purchase_request.requester.email],
        html_message=html_message,
        fail_silently=False
    )

def send_rejection_notification(purchase_request, comment):
    """
    Sends rejection notification with reason
    """
    try:
        requester = purchase_request.requester
        items = purchase_request.items.all()
        area_manager = purchase_request.area_manager
        context = {
            'request_id': f"PR-{purchase_request.id:04d}",
            'requester_name': requester.get_full_name(),
            'voucher_id': getattr(purchase_request, 'voucher_id'),
            'rejector_name': purchase_request.area_manager.get_full_name(),
            'rejection_reason': comment.text if comment else "No reason provided.",
            'items': items, 
            'rejection_date': purchase_request.area_manager_declined_at.strftime("%b %d, %Y %I:%M %p"),
            'company_name': settings.COMPANY_NAME,
            'store_name': purchase_request.store.name,
            'total_amount': f"₦{purchase_request.total_amount:,.2f}",
            'request_date': purchase_request.created_at.strftime("%b %d, %Y %I:%M %p"),
            'status': purchase_request.get_status_display()
        }
        
        html_message = render_to_string('pr_rejection.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f"Purchase Request Declined - {context['request_id']}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[purchase_request.requester.email],
            html_message=html_message
        )

    except Exception as err:
        logger.error(err)
        raise
    
def send_creation_notification(purchase_request):
    """
    Sends creation notification to requester with request details
    """
    try:
        #get the store area manager for the purchase request
        print("sending email notification ...")
        purchase_request_id = f"{purchase_request.id:04}"
        print("Purchase Request ID", purchase_request_id)
        store = purchase_request.store
        print("Area Manager ==> ", store.area_manager)
        area_manager = store.area_manager if store.area_manager else None
        if area_manager:
            context = {
                'request_id': f"PR-{purchase_request_id}",
                'area_manager_name': area_manager.get_full_name(),
                'store_name': purchase_request.store.name,
                'store_code': purchase_request.store.code,
                'total_amount': f"₦{purchase_request.total_amount:,.2f}",
                'request_date': purchase_request.created_at.strftime("%b %d, %Y %I:%M %p"),
                'status': purchase_request.get_status_display(),
                'company_name': settings.COMPANY_NAME
            }
          
            html_message = render_to_string('pr_creation.html', context)
            plain_message = strip_tags(html_message)

            send_mail(
                subject=f"Purchase Request Created - {purchase_request_id}",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[area_manager.email],
                html_message=html_message
            )

    except Exception as err:
        logger.error(err)
    

def send_reimbursement_creation_notification(reimbursement):
    try:
        # area_manager FK on the reimbursement is only set upon approval.
        # The correct contact on creation is the store's assigned area manager.
        area_manager = reimbursement.store.area_manager if reimbursement.store else None
        if not area_manager:
            logger.warning(
                f"Reimbursement {reimbursement.id}: store has no area manager assigned, skipping creation email."
            )
            return

        context = {
            'request_id': f"RR-{reimbursement.id:04d}",   # ✅ FIX: was "PR-" prefix
            'area_manager_name': area_manager.get_full_name(),
            'store_name': reimbursement.store.name,
            'store_code': reimbursement.store.code,
            'total_amount': f"₦{reimbursement.total_amount:,.2f}",
            'request_date': reimbursement.created_at.strftime("%b %d, %Y %I:%M %p"),
            'status': reimbursement.get_status_display(),
            'company_name': settings.COMPANY_NAME
        }

        html_message = render_to_string('rr_creation.html', context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=f"Reimbursement Request Created - {context['request_id']}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[area_manager.email],
            html_message=html_message
        )
    except Exception as err:
        logger.error(f"Failed to send reimbursement creation notification: {err}")
        raise

    
def send_reimbursement_approval_notification(reimbursement, user):
    """
    Area Manager approval  → notifies: (1) requester, (2) all Internal Control users
    Internal Control approval → 
    notifies: area manager of the store
    """
    requester = User.objects.get(id=reimbursement.requester_id)
    store_area_manager = reimbursement.store.area_manager

    context = {
        'request_id': f"RR-{reimbursement.id:04d}",
        'store_name': reimbursement.store.name,
        'store_code': reimbursement.store.code,
        'area_manager_approvedby_name': reimbursement.area_manager.get_full_name() if reimbursement.area_manager else "N/A",
        'internal_control_approvedby_name': reimbursement.internal_control.get_full_name() if reimbursement.internal_control else "N/A",
        'total_amount': f"₦{reimbursement.total_amount:,.2f}",
        'items': reimbursement.items.all(),
        'area_manager_approval_date': reimbursement.area_manager_approved_at.strftime("%b %d, %Y %I:%M %p") if reimbursement.area_manager_approved_at else "N/A",
        'internal_control_approval_date': reimbursement.internal_control_approved_at.strftime("%b %d, %Y %I:%M %p") if reimbursement.internal_control_approved_at else "N/A",
        'internal_control_status': reimbursement.get_internal_control_status_display(),
        'status': reimbursement.get_status_display(),
        'request_date': reimbursement.created_at.strftime("%b %d, %Y %I:%M %p"),
        'company_name': settings.COMPANY_NAME,
    }

    if user.role.name == "Area Manager":
        context['name'] = requester.get_full_name()

        #Notify the requester
        html_message = render_to_string('am_reimbursement_approval.html', context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject=f"Reimbursement Request Approved - {context['request_id']}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[requester.email],
            html_message=html_message,
            fail_silently=False,
        )

        # Notify all Internal Control users that a new RR needs their review
        ic_role = Role.objects.filter(name="Internal Control").first()
        if ic_role:
            ic_users = User.objects.filter(role=ic_role, is_active=True)
            ic_emails = list(ic_users.values_list('email', flat=True))
            if ic_emails:
                context['name'] = "Internal Control Team"
                ic_html = render_to_string('am_reimbursement_approval.html', context)
                ic_plain = strip_tags(ic_html)
                send_mail(
                    subject=f"Reimbursement Request Ready for IC Review - {context['request_id']}",
                    message=ic_plain,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=ic_emails,
                    html_message=ic_html,
                    fail_silently=False,
                )

    elif user.role.name == "Internal Control":
        context['name'] = store_area_manager.get_full_name() if store_area_manager else "Area Manager"
        html_message = render_to_string('ic_reimbursement_approval.html', context)
        plain_message = strip_tags(html_message)
        recipient = store_area_manager.email if store_area_manager else None
        if recipient:
            send_mail(
                subject=f"Reimbursement Request Approved - {context['request_id']}",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                html_message=html_message,
                fail_silently=False,
            )
def send_reimbursement_rejection_notification(reimbursement, user, comment):
    """
    Sends rejection notification with reason
    """
    
    area_manager = reimbursement.store.area_manager # Get the area manager of the store that made the request
    
    items = reimbursement.items.all()
    requester = User.objects.get(id=reimbursement.requester_id)
    
    if user.role.name == "Area Manager":
        name = requester.get_full_name()
        rejector = reimbursement.area_manager.get_full_name() if reimbursement.area_manager else "N/A"
        # comments =  reimbursement.comments.filter(author=reimbursement.area_manager).order_by('-created_at').first()
        rejection_date = reimbursement.area_manager_declined_at
        status = reimbursement.get_status_display()
        request_date = reimbursement.created_at.strftime("%b %d, %Y %I:%M %p"),
        
    elif user.role.name == "Internal Control":
        name = area_manager.get_full_name()
        rejector = reimbursement.internal_control.get_full_name() if reimbursement.internal_control else "N/A"
        # comments =  reimbursement.comments.filter(author=reimbursement.internal_control).order_by('-created_at').first()
        rejection_date = reimbursement.internal_control_declined_at
        status = reimbursement.get_internal_control_status_display()
        request_date = reimbursement.area_manager_approved_at.strftime("%b %d, %Y %I:%M %p") if reimbursement.area_manager_approved_at else "N/A",
        
    context = {
        'request_id': f"RR-{reimbursement.id:04d}",
        'name':name,
        'rejector_name': rejector,
        'rejection_reason': comment if comment else "No reason provided.",
        'items': items, 
        'rejection_date': rejection_date,
        'company_name': settings.COMPANY_NAME,
        'store_name': reimbursement.store.name,
        'total_amount': f"₦{reimbursement.total_amount:,.2f}",
        'request_date': request_date,
        'status': status
    }
    
     # Dynamic allocation of receipient and appropriate html template.
    if user.role.name == "Area Manager":
        receipient = requester.email
        html_template = 'reimbursement_rejection.html'
        
    elif user.role.name == "Internal Control":
        receipient = area_manager.email
        html_template = 'reimbursement_rejection.html'


    html_message = render_to_string(html_template, context)
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=f"Reimbursement Request Declined - {context['request_id']}",
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[receipient],
        html_message=html_message
    )
    
    
    