import logging
from django.db import models
from django.utils import timezone
form datetime import datetime
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError
from decimal import Decimal

logger = logging.getLogger(__name__)

class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name

class Store(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='region_stores')
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)  # track when store created
    updated_at = models.DateTimeField(auto_now=True)      # track last modified
    is_active = models.BooleanField(default=True)
    restaurant_manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_stores'
    )
    area_manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='area_manager_stores'
    )
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'region'], name='unique_store_in_region')
        ]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - ({self.code})"
    
    #on creation, set balance to budget
    def save(self, *args, **kwargs):
        if not self.pk:  # only set balance on creation
            self.balance = self.budget
        super().save(*args, **kwargs)

    @cached_property
    def balance(self):
        """Get the entire balance of the store."""
        approved_expenses = self.reimbursements.filter(internal_control_status='approved')
        total_approved = approved_expenses.aggregate(total=models.Sum('total_amount'))['total']
        remaining_balance = (self.balance - total_approved) if total_approved else self.balance
        return remaining_balance
    
   
    def _get_current_week(self):
        """Get the number of the current week. """
        today = datetime.date.today()
        iso_calendar = today.isocalendar()
        return iso_calendar[1]
    
    def allocate(self, amount):
        try:
            # Check that amount is provided.
            if not amount:
                raise ValidationError("Allocation amount must be provided.")
            
            # Invalidate previous allocations
            self.allocations.update(is_current=False)
            # Create New allocation
            current_week = self._get_current_week()
            allocation = Allocation.objects.create(store=self, amount=amount, 
                week=current_week, is_current=True)
            
            return allocation
        
        except Exception as err:
            logger.error(err)
            raise

class Allocation(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="allocations")
    amount = models.FloatField()
    date = models.DateTimeField(auto_now_add=True)
    week = models.PositiveSmallIntegerField()
    is_current = models.BooleanField(default=False)

class Transaction(models.Model):
    allocation = models.ForeignKey(Allocation, related_name='transactions')
    approved_expense = models.FloatField(default=0.0)
    balance = models.FloatField(default=models.F("amount"))
    date = models.DateTimeField(auto_now_add=True)


class StoreBudgetHistory(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="budget_history")
    previous_budget = models.DecimalField(max_digits=12, decimal_places=2)
    new_budget = models.DecimalField(max_digits=12, decimal_places=2)
    comment = models.CharField(max_length=225, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        'users.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budget_updates"
    )

    def __str__(self):
        return f"{self.store.name}: {self.previous_budget} → {self.new_budget} on {self.changed_at:%Y-%m-%d}"
