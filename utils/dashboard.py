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

class DashboardView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewAnalytics]
    
    def _get_user_stores(self, user, store_param=None):
        # Return queryset/list of Store objects this user should see
        if store_param:
            try:
                return Store.objects.filter(id=int(store_param))
            except Exception:
                return Store.objects.none()
        stores = Store.objects.all()
        role_name = getattr(getattr(user, "role", None), "name", "").strip() if user else ""
        if role_name == "Restaurant Manager":
            return stores.filter(id=getattr(user, "store_id", None))
        if role_name == "Area Manager":
            return user.assigned_stores.all()
        # default: all stores
        return stores

    def get(self, request):
        user = request.user
        # parse month/year with validation (falls back to current)
        now = timezone.now()
        try:
            month = int(request.query_params.get("month", now.month))
            year = int(request.query_params.get("year", now.year))
            if not (1 <= month <= 12) or not (1900 <= year <= 2100):
                raise ValueError("Invalid month or year")
        except (ValueError, TypeError):
            month, year = now.month, now.year

        # optional store filter (single store id)
        store_param = request.query_params.get("store")

        # determine month range for consistency (entire selected month)
        start_month = timezone.make_aware(datetime(year, month, 1))
        if month == 12:
            end_month = timezone.make_aware(datetime(year + 1, 1, 1)) - timedelta(days=1)
        else:
            end_month = timezone.make_aware(datetime(year, month + 1, 1)) - timedelta(days=1)

        stores = self._get_user_stores(user, store_param)

        # Monthly expenses (sum of reimbursement amounts for stores and month range)
        monthly_expenses = (
            Reimbursement.objects.filter(
                store__in=stores,
                created_at__date__range=[start_month.date(), end_month.date()]
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
        )

        # Monthly income (budget allocations for stores)
        monthly_income = stores.aggregate(total_budget=Sum("budget"))["total_budget"] or Decimal(0)
        monthly_balance = monthly_income - Decimal(monthly_expenses or 0)

        # Imprest amount - try to read from Store.imprest_amount or fallback to 0
        # (adjust attribute name if different in your Store model)
        imprest_amount = LimitConfig.objects.first()
        try:
            imprest_amount = imprest_amount.limit
        except Exception:
            CustomValidationException(False, "could not read limit")

        # Top monthly purchases by item name (from ReimbursementItem)
        top_monthly_qs = (
            ReimbursementItem.objects.filter(
                reimbursement__store__in=stores,
                reimbursement__created_at__date__range=[start_month.date(), end_month.date()]
            )
            .values("item_name")
            .annotate(total_spent=Sum("item_total"))
            .order_by("-total_spent")[:5]
        )
        top_monthly_purchases = [
            {"item_name": r["item_name"], "total_spent": r["total_spent"]} for r in top_monthly_qs
        ]

        # Monthly trend for selected year (Reimbursement totals per month)
        line_qs = (
            Reimbursement.objects.filter(
                store__in=stores,
                created_at__year=year
            )
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(total=Sum("total_amount"))
            .order_by("month")
        )
        # normalize to 12 months (fill missing months with 0)
        monthly_totals = {int(r["month"]): (r["total"] or 0) for r in line_qs}
        line_chart_data = [{"month": m, "total": monthly_totals.get(m, 0)} for m in range(1, 13)]

        data = {
            "monthly_balance": float(monthly_balance),
            "monthly_expenses": float(monthly_expenses),
            "imprest_amount": float(imprest_amount),
            "top_monthly_purchases": top_monthly_purchases,
            "line_chart_data": line_chart_data,
            "stores_count": stores.count()
        }

        return CustomResponse(True, "Dashboard data fetched successfully", 200, data)

