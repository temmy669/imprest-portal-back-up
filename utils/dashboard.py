from .permissions import *
from helpers.response import CustomResponse
from rest_framework.views import APIView
from purchases.models import PurchaseRequest
from reimbursements.models import Reimbursement
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import timedelta, datetime
from users.auth import JWTAuthenticationFromCookie
from django.utils.timezone import make_aware
from django.db.models import Sum




from django.db.models import Sum

class DashboardView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewAnalytics]
    
    
    def get(self, request):
        now = timezone.now()
        start_week = now - timedelta(days=now.weekday())  # Monday
        end_week = start_week + timedelta(days=6)
        user = request.user

        # --- Weekly Expenses ---
        weekly_expenses = (
            Reimbursement.objects.filter(created_at__date__range=[start_week, end_week])
            .aggregate(total=Sum("amount"), store__in=user.assigned_stores.all())
        )["total"] or 0

        # --- Weekly Income (placeholder if you have an income model) ---
        weekly_income = 0  

        # --- Weekly Balance ---
        weekly_balance = weekly_income - weekly_expenses

        # --- Imprest Amount (from Store model if you keep it there) ---
        imprest_amount = 0  # replace with real query

        # --- Top Weekly Expenses (with item names) ---
        top_expenses = (
            Reimbursement.objects.filter(created_at__date__range=[start_week, end_week])
            .values("item__name")  # assuming Reimbursement has FK to Item
            .annotate(total_spent=Sum("amount"))
            .order_by("-total_spent")[:5]
        )

        # --- Line Chart Data (monthly expenses trend for the year) ---
        line_chart_data = (
            Reimbursement.objects.filter(created_at__year=now.year)
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )

        return CustomResponse(
            True, "Dashboard data fetched successfully",
            data={
                "weekly_balance": weekly_balance,
                "weekly_expenses": weekly_expenses,
                "imprest_amount": imprest_amount,
                "top_weekly_expenses": list(top_expenses),
                "line_chart_data": list(line_chart_data),
            },
        )
