from .permissions import *
from helpers.response import CustomResponse
from rest_framework.views import APIView
from purchases.models import PurchaseRequest
from reimbursements.models import Reimbursement, ReimbursementItem
from stores.models import Store
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import timedelta, datetime
from users.auth import JWTAuthenticationFromCookie
from django.utils.timezone import make_aware


class DashboardView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewAnalytics]


    def get(self, request):
        now = timezone.now()
        start_week = now - timedelta(days=now.weekday())  # Monday
        end_week = start_week + timedelta(days=6)
        user = request.user
        assigned_stores = user.assigned_stores.all()

        # --- Weekly Expenses ---
        weekly_expenses = (
            Reimbursement.objects.filter(
                created_at__date__range=[start_week.date(), end_week.date()],
                store__in=assigned_stores
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )

        # --- Weekly Income (placeholder if you have an income model) ---
        # Assuming income comes from approved PurchaseRequests
        weekly_income = (
            PurchaseRequest.objects.filter(
                created_at__date__range=[start_week.date(), end_week.date()],
                store__in=assigned_stores,
                status='approved'
            ).aggregate(total=Sum("total_amount"))["total"] or 0
        )

        # --- Weekly Balance ---
        weekly_balance = weekly_income - weekly_expenses

        # --- Imprest Amount (sum of balances from assigned stores) ---
        imprest_amount = (
            Store.objects.filter(id__in=assigned_stores).aggregate(
                total=Sum("balance")
            )["total"] or 0
        )

        # --- Top Weekly Expenses (with item names from ReimbursementItem) ---
        top_expenses = (
            ReimbursementItem.objects.filter(
                reimbursement__created_at__date__range=[start_week.date(), end_week.date()],
                reimbursement__store__in=assigned_stores
            ).values("item_name")
            .annotate(total_spent=Sum("item_total"))
            .order_by("-total_spent")[:5]
        )

        # --- Line Chart Data (monthly expenses trend for the year) ---
        line_chart_data = (
            Reimbursement.objects.filter(
                created_at__year=now.year,
                store__in=assigned_stores
            ).annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(total=Sum("total_amount"))
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
