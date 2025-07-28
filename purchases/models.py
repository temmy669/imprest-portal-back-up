from django.db import models
from django.contrib.auth import get_user_model
from stores.models import Store
from users.models import User

class PurchaseRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]
    
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchase_requests')
    store = models.ForeignKey(Store, on_delete=models.CASCADE) 
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    comment = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PR-{self.id} - {self.status} by {self.requester.first_name} {self.requester.last_name}"

class PurchaseRequestItem(models.Model):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name='items')
    gl_code = models.CharField(max_length=10)  # From Appendix 2
    expense_item = models.CharField(max_length=100)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

class Comment(models.Model):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']