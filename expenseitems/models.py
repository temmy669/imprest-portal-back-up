from django.db import models

# Create your models here.
class ExpenseItem(models.Model):
    name = models.CharField(max_length=225)
    gl_code = models.CharField(max_length=10, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    