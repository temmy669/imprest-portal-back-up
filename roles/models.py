from django.db import models

# Create your models here.

class Permission(models.Model):
    """
    Custom permissions table for business-specific rules
    (e.g., "can_approve_above_5000", "can_view_all_stores")
    """
    codename = models.CharField(max_length=100, unique=True)  
    name = models.CharField(max_length=255) 
    
    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        related_name='roles',
        blank=True
    )
    
    def str__(self):
        return self.name
    
