from .permissions import *
from helpers.response import CustomResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
import calendar

from reimbursements.models import Reimbursement, ReimbursementItem
from stores.models import Store
from users.auth import JWTAuthenticationFromCookie


class DashboardView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewAnalytics]

    # -------------------------------
    # Helpers
    # -------------------------------
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
            return Store.objects.all()
        return Store.objects.all()
    
    def _get_current_week(self):
        """A method to get the current week. """
        today = timezone.now().date()
        iso_calendar = today.isocalendar()
        current_week_number = iso_calendar[1]
        print("Current week number ==> ", current_week_number)
        return current_week_number
        

    def _get_period_range(self, year, month, week_number=None):
        """Return start and end datetime of the given period (week) in a month. 
        :week_number: refers to the number of the selected week.
        - this defaults to the current week.
        """
        day = 1
        first_day = datetime(year, month, day)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        start = first_monday + timedelta(weeks=week_number - 1)
        end = start + timedelta(days=6)

        # Trim end if it passes month
        last_day_of_month = datetime(year, month + 1, 1) - timedelta(days=1) if month != 12 else datetime(year, month, 31)
        if end > last_day_of_month:
            end = last_day_of_month
            
        return timezone.make_aware(start), timezone.make_aware(end)

    def _get_available_periods(self, stores, year, month):
        """Return list of periods with start/end dates and open/closed status. 
        """
        periods = []
        first_day = datetime(year, month, 1)
        first_monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7)
        current_start = first_monday
        period_number = 1

        while current_start.month == month:
            current_end = current_start + timedelta(days=6)
            last_day_of_month = datetime(year, month + 1, 1) - timedelta(days=1) if month != 12 else datetime(year, month, 31)
            if current_end > last_day_of_month:
                current_end = last_day_of_month 
            reimbursements = Reimbursement.objects.filter(
                store__in=stores,
                created_at__range=(timezone.make_aware(current_start), timezone.make_aware(current_end))
            )
            period_closed = not reimbursements.filter(disbursement_status="pending").exists()
            periods.append({
                "period": period_number,
                "start": current_start.date().isoformat(),
                "end": current_end.date().isoformat(),
                "status": "closed" if period_closed else "open"
            })
            current_start = current_start + timedelta(days=7)
            period_number += 1

        return periods

    # -------------------------------
    # Main
    # -------------------------------
    def get(self, request):
        user = request.user
        now = timezone.now()

        # ---- Parse filters ----
        try:
            current_week = self._get_current_week()

            month = int(request.query_params.get("month", now.month))
            year = int(request.query_params.get("year", now.year))
            period = int(request.query_params.get("period", current_week))

        except Exception:
            month, year, period = now.month, now.year, 1

        store_param = request.query_params.get("store")
        stores = self._get_user_stores(user, store_param)

        # ---- Period range ----
        period_start, period_end = self._get_period_range(year, month, period)

        # ---- Total Imprest (Store Budget) ----
        total_imprest = stores.filter(date__range=(period_end, period_end)).aggregate(total=Sum("budget"))["total"] or Decimal(0)

        # WHAT YOU NEED IS THE TOTAL WEEKLY IMPRESS

        # ---- Weekly Expenses (pending only) ----
        weekly_expenses = (
            Reimbursement.objects.filter(
                store__in=stores,
                created_at__range=(period_start, period_end),
                disbursement_status="pending",
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
        )

        weekly_balance = total_imprest - weekly_expenses

        # ---- Period status ----
        period_closed = not Reimbursement.objects.filter(
            store__in=stores,
            created_at__range=(period_start, period_end),
            disbursement_status="pending",
        ).exists()

        # ---- Top purchases in selected month ----
        start_month = timezone.make_aware(datetime(year, month, 1))
        end_month = timezone.make_aware(datetime(year + 1, 1, 1)) - timedelta(days=1) if month == 12 else timezone.make_aware(datetime(year, month + 1, 1)) - timedelta(days=1)

        top_monthly_purchases = list(
            ReimbursementItem.objects.filter(
                reimbursement__store__in=stores,
                reimbursement__created_at__range=(start_month, end_month),
            )
            .values("item_name")
            .annotate(total_spent=Sum("item_total"))
            .order_by("-total_spent")[:5]
        )

        # ---- Line chart (yearly) ----
        line_qs = (
            Reimbursement.objects.filter(
                store__in=stores,
                created_at__year=year,
            )
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(total=Sum("total_amount"))
            .order_by("month")
        )

        monthly_totals = {int(i["month"]): float(i["total"]) for i in line_qs}

        line_chart_data = [
            {"month": calendar.month_name[m], "total": monthly_totals.get(m, 0)}
            for m in range(1, 13)
        ]

        # ---- Available periods for frontend ----
        available_periods = self._get_available_periods(stores, year, month)

        # ---- Response ----
        return CustomResponse(
            True,
            "Dashboard data fetched successfully",
            200,
            {
                "role": user.role.name if user.role else None,
                "stores_count": stores.count(),
                "period": f"Week {period}",
                "period_status": "closed" if period_closed else "open",
                "weekly_expenses": float(weekly_expenses),
                "weekly_balance": float(weekly_balance),
                "total_imprest": float(total_imprest),
                "top_monthly_purchases": top_monthly_purchases,
                "line_chart_data": line_chart_data,
                "available_periods": available_periods,
            },
        )
