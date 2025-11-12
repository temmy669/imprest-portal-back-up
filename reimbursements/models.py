from django.db import models
from users.models import User
from stores.models import Store
from purchases.models import PurchaseRequest
from banks.models import Bank, Account
from decimal import Decimal

# Create your models here.
STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('disbursed', 'Disbursed'),
    ]


class Reimbursement(models.Model):
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reimbursements')
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_draft = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_reimbursements')

    # Approvals
    area_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='area_manager_reimbursements')
    area_manager_approved_at = models.DateTimeField(null=True, blank=True)
    area_manager_declined_at = models.DateTimeField(null=True, blank=True)
    internal_control = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='internal_control_reimbursements')
    internal_control_approved_at = models.DateTimeField(null=True, blank=True)
    internal_control_declined_at = models.DateTimeField(null=True, blank=True)
    internal_control_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reimbursement_updates')
    disbursement_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    treasurer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='treasurer_reimbursements')
    disbursed_at = models.DateTimeField(null=True, blank=True)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    # link to PRs (for items >= 5000)
    purchase_requests = models.ManyToManyField(PurchaseRequest, blank=True, related_name='reimbursements')
    def save(self, *args, user=None, **kwargs):
        if user:
            self.updated_by = user
            if not self.pk:  # new object being created
                self.requester = user
        super().save(*args, **kwargs)
    
class ReimbursementItem(models.Model):
    reimbursement = models.ForeignKey(Reimbursement, on_delete=models.CASCADE, related_name='items')
    purchase_request_ref = models.CharField(max_length=100, blank=True, null=True)
    gl_code = models.CharField(max_length=50, blank=True, null=True)
    item_name = models.CharField(max_length=255)
    transportation_from = models.CharField(max_length=255, default='Not Applicable')
    transportation_to = models.CharField(max_length=255, default='Not Applicable')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    item_total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    internal_control_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    receipt = models.CharField(max_length=255, null=True, blank=True)
    requires_receipt = models.BooleanField(default=False)
    
    
class ReimbursementComment(models.Model):
    reimbursement = models.ForeignKey(Reimbursement, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.TextField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    system_generated = models.BooleanField(default=False)


