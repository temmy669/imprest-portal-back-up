from rest_framework import serializers
from .models import Bank, Account

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ['id', 'bank_name', 'bank_short_code', 'status', 'gl_code', 'created_at', 'updated_at']

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['id', 'bank', 'account_number', 'account_name', 'status', 'created_at', 'updated_at']