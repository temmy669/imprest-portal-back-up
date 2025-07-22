from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from roles.models import Role
from stores.models import Store

class User(AbstractUser):
    microsoft_ad_id = models.CharField(
        max_length=255, 
        unique=True, 
        null=True, 
        blank=True,
        help_text=_("The unique identifier for the user from Microsoft Azure AD.")
    )
    name = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text=_("The full name of the user.")
    )
    
    first_name = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )
    
    last_name = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )
    
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
    )

    assigned_stores = models.ManyToManyField(
        Store,
        blank=True,
        related_name='assigned_users'
    )
    
    is_active = models.BooleanField(default=True)
    
    data_updated_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text=_("The last time the user's profile data was updated.")
    )

    def save(self, *args, **kwargs):
        """Custom save method to update `data_updated_at`."""
        self.data_updated_at = timezone.now()
        super().save(*args, **kwargs)


    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")



class OAuthState(models.Model):
    state = models.CharField(max_length=100, unique=True)
    pkce_verifier = models.CharField(max_length=128)  # PKCE verifiers are typically 43-128 chars
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['created_at'])
        ]

    @classmethod
    def cleanup_expired(cls, max_age_minutes=10):
        """Clean up expired state entries"""
        expiration_time = timezone.now() - timedelta(minutes=max_age_minutes)
        cls.objects.filter(created_at__lt=expiration_time).delete()
