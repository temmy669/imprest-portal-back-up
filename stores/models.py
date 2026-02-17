import logging
from django.db import models
from datetime import date
from django.utils import timezone
from datetime import datetime
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
    
   
    def _get_current_week_year(self):
        """Get the number of the current week. """
        today = timezone.now().date()
        iso_calendar = today.isocalendar()
        return iso_calendar.week
    
    def _get_current_week_month(self):
        """
            Calculates the week number of the month based on ISO week numbering 
            (Monday as the first day of the week by default).
        """
        # Get the ISO week number of the current date
        date_ = timezone.now().date()
        calendar = date_.isocalendar()
        current_week_of_year = calendar.week
        
        # Get the ISO week number of the first day of the month
        first_day_of_month = date(date_.year, date_.month, 1)
        _, first_day_week_of_year, _ = first_day_of_month.isocalendar()
        
        # If the first week of the month belongs to the previous year's last week (ISO standard behavior),
        # the simple subtraction needs adjustment. However, for a basic calculation:
        
        # This subtraction gives the difference in week numbers. Add 1 because we're 1-indexing the weeks.
        week_in_month = current_week_of_year - first_day_week_of_year + 1
        
        # Handle edge case where the current week of year is smaller than the first day's (e.g., year boundary)
        if week_in_month < 1:
            # This typically means the date belongs to the 'previous month's' partial week 
            # in the context of ISO week numbering, so we set it to 1.
            week_in_month = 1 
        return week_in_month
    
    def can_raise_expense(self, amount):
        """Check if a user can raise expense. 
        A user can only raise expense if the store balance is greater than or equal to 
        the intended expense amount.
        """
        last_allocation = self.allocations.filter(is_current=True).last()
        if last_allocation and last_allocation.balance >= amount:
            return True
        return False
    
    def allocate(self, amount):
        try:
            # Check that amount is provided.
            if not amount:
                raise ValidationError("Allocation amount must be provided.")
            
            # Invalidate previous allocations
            allocations = self.allocations.all()
            allocations.update(is_current=False)
            last_allocation = allocations.last()

            # Create New allocation
            # get the current week number
            current_week = self._get_current_week()
            allocation = Allocation.objects.create(store=self, amount=amount, 
                week=current_week, is_current=True)
            allocation.balance = last_allocation.balance + amount
            allocation.save()
            
            return allocation
        
        except Exception as err:
            logger.error(err)
            raise

class Allocation(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="allocations")
    amount = models.FloatField()
    balance = models.FloatField(default=0)
    date = models.DateTimeField(auto_now_add=True)
    year_week = models.PositiveSmallIntegerField(blank=True, null=True)
    month_week = models.PositiveBigIntegerField(blank=True, null=True)
    is_current = models.BooleanField(default=False)

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
