from .permissions import *
from helpers.response import CustomResponse
from rest_framework.views import APIView
from purchases.models import PurchaseRequest
from reimbursements.models import Reimbursement, ReimbursementItem
from stores.models import Store
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, F
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import timedelta, datetime
from users.auth import JWTAuthenticationFromCookie
from decimal import Decimal
from purchases.models import LimitConfig
import calendar

class DashboardView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewAnalytics]

    def _get_user_stores(self, user, store_param=None):
        if store_param:
            try:
                store_ids = [int(s) for s in store_param.split(",")]
                return Store.objects.filter(id__in=store_ids)
            except Exception:
                return Store.objects.none()

        role_name = getattr(getattr(user, "role", None), "name", "").strip()

        if role_name == "Restaurant Manager":
            return Store.objects.filter(id=user.store_id)

        if role_name == "Area Manager":
            return user.assigned_stores.all()
        
        if role_name == "Internal Control":
            return Store.objects.filter(id__in=store_ids) if store_param else Store.objects.all()


        return Store.objects.all()


    def get(self, request):
        user = request.user
        now = timezone.now()

        # Parse month & year
        try:
            month = int(request.query_params.get("month", now.month))
            year = int(request.query_params.get("year", now.year))
        except:
            month, year = now.month, now.year

        # Store filter (for Area Managers)
        store_param = request.query_params.get("store")  # e.g. "1,3,5"

        # Set date range for month
        start_month = timezone.make_aware(datetime(year, month, 1))
        end_month = (
            timezone.make_aware(datetime(year + 1, 1, 1)) - timedelta(days=1)
            if month == 12 else
            timezone.make_aware(datetime(year, month + 1, 1)) - timedelta(days=1)
        )

        stores = self._get_user_stores(user, store_param)

        # --- Calculations ---

        # Total reimbursements (monthly expenses)
        start_week = now - timedelta(days=now.weekday())  # Monday
        end_week = start_week + timedelta(days=6)        # Sunday
        weekly_expenses = (
            Reimbursement.objects.filter(
                store__in=stores,
                created_at__date__range=[start_week.date(), end_week.date()]
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
        )

        # Store budget / Imprest configuration
        budget = stores.aggregate(total_budget=Sum("budget"))["total_budget"] or Decimal(0)
        weekly_balance = budget - weekly_expenses

        imprest_amount = LimitConfig.objects.first()
        imprest_amount = imprest_amount.limit if imprest_amount else Decimal(0)

        # Top 5 purchases this month
        top_monthly_purchases = list(
            ReimbursementItem.objects.filter(
                reimbursement__store__in=stores,
                reimbursement__created_at__date__range=[start_month.date(), end_month.date()]
            ).values("item_name")
             .annotate(total_spent=Sum("item_total"))
             .order_by("-total_spent")[:5]
        )

        # Line chart data for the selected year
        line_qs = (
                Reimbursement.objects.filter(
                    store__in=stores,
                    created_at__year=year
                )
                .annotate(month=ExtractMonth("created_at"))  # Add dynamic field first
                .values('month')                             # Now group by that new field
                .annotate(total=Sum('total_amount'))         # Then aggregate
                .order_by('month')
            )


        monthly_totals = {int(item["month"]): float(item["total"]) for item in line_qs}
    
        line_chart_data = [
                    {
                        "month": calendar.month_name[m],  # e.g. "January"
                        "total": monthly_totals.get(m, 0)
                    }
                    for m in range(1, 13)
                ]

        # --- Final Response ---
        return CustomResponse(
            True,
            "Dashboard data fetched successfully",
            200,
            {
                "role": user.role.name if user.role else None,
                "stores_count": stores.count(),
                "weekly_balance": float(weekly_balance),
                "weekly_expenses": float(weekly_expenses),
                "imprest_amount": float(budget),
                "top_monthly_purchases": top_monthly_purchases,
                "line_chart_data": line_chart_data,
            }
        )
