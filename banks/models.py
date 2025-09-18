import uuid
from django.db import models

class Bank(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_name = models.CharField(max_length=100, unique=True)
    bank_short_code = models.CharField(max_length=30, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def toggle_status(self):
        """Toggle bank status between active and inactive."""
        self.status = "inactive" if self.status == "active" else "active"
        self.save()

    def __str__(self):
        return f"{self.bank_name} ({self.status})"

class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name='accounts')
    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Bank.STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account_name} - {self.account_number}"
