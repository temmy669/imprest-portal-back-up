from django.db import models



class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)
    area_managers = models.ManyToManyField(
        'users.User',
        related_name='managed_regions'
    )

    def __str__(self):
        return self.name

class Store(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='region_stores')
    restaurant_manager = models.ForeignKey(
    'users.User',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='managed_store'  # no clash with assigned_stores
)
    
    area_manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='area_manager_stores'
    )
    
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [['name', 'region']]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - ({self.code})"