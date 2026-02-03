from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from decimal import Decimal


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
    def store_balance(self):
        """Get the entire balance of the store."""
        pass

    @cached_property
    def weekly_balance(self, week_number):
        """Get the balance for the specified week. """
        pass


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
