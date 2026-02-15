from .permissions import *
from datetime import date
from helpers.response import CustomResponse
from rest_framework.views import APIView
from purchases.models import PurchaseRequest
from reimbursements.models import Reimbursement, ReimbursementItem
from stores.models import Store
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, F, Q
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

    def _get_user_stores(self, user, store_IDs=None):
        """Get stores based on user role and optional store filter"""
        role_name = getattr(getattr(user, "role", None), "name", "").strip()
        print("user role", role_name)

        if role_name == "Restaurant Manager":
            return Store.objects.filter(id=user.store_id)
        
        if store_IDs:
            try:
                if role_name == "Area Manager":
                    return user.assigned_stores.filter(id__in=store_IDs)
                else:
                    return Store.objects.filter(id__in=store_IDs)
            except Exception:
                return Store.objects.none()
            
        if role_name == "Area Manager":
            return user.assigned_stores.all()
        return Store.objects.all()

    def _get_week_range(self, year, month, week_number):
        """
        Calculate the start and end dates for a specific week in a month.
        Weeks start on Monday and end on Sunday.
        """
        # Get first day of the month
        first_day = datetime(year, month, 1)
        
        # Find the first Monday of the month
        days_until_monday = (7 - first_day.weekday()) % 7
        if first_day.weekday() != 0:  # If not Monday
            first_monday = first_day + timedelta(days=days_until_monday)
        else:
            first_monday = first_day
        
        # Calculate week start
        week_start = first_monday + timedelta(weeks=week_number - 1)
        
        # Ensure we're still in the target month
        if week_start.month != month:
            week_start = first_day
        
        # Calculate week end (Sunday)
        week_end = week_start + timedelta(days=6)
        
        # Get last day of month
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        
        # Ensure week_end doesn't exceed month boundary
        if week_end > last_day:
            week_end = last_day
        
        return timezone.make_aware(week_start), timezone.make_aware(week_end.replace(hour=23, minute=59, second=59))

    def _get_current_accounting_period(self, stores):
        """
        Get the current accounting period (week) that hasn't been reimbursed yet.
        Returns the start date of the oldest unreimbursed period.
        """
        # Find the most recent reimbursement approval date for these stores
        last_reimbursement = (
            Reimbursement.objects.filter(
                store__in=stores,
                status='disbursed'
            )
            .order_by('-disbursed_at')
            .first()
        )
        
        if last_reimbursement and last_reimbursement.disbursed_at:
            # Period starts the Monday after last reimbursement
            last_date = last_reimbursement.disbursed_at.date()
            days_since_monday = last_date.weekday()
            period_start = last_date - timedelta(days=days_since_monday) + timedelta(weeks=1)
        else:
            # If No reimbursement yet, use the first Monday of current month or 
            # earliest approved expense
            first_expense = (
                PurchaseRequest.objects.filter(store__in=stores, status="approved")
                .order_by('created_at')
                .first()
            )
            
            if first_expense:
                expense_date = first_expense.created_at.date()
                days_since_monday = expense_date.weekday()
                period_start = expense_date - timedelta(days=days_since_monday)
            else:
                # Default to current week's Monday
                now = timezone.now().date()
                days_since_monday = now.weekday()
                period_start = now - timedelta(days=days_since_monday)
        
        return timezone.make_aware(datetime.combine(period_start, datetime.min.time()))
    
    def _get_current_week_year(self):
        """Get the weekn number for the current week. """
        date_ = timezone.now().date()
        calendar = date_.isocalendar()
        return calendar.week
    
    def _get_current_week_month(self):
        """
            Calculates the week number of the month based on ISO week numbering 
            (Monday as the first day of the week by default).
        """
        # Get the ISO week number of the current date
        date_ = timezone.now().date()
        calendar = date_.isocalendar()
        current_week_of_year = calendar.week
        
        # Get the ISO week number of the first day of the month
        first_day_of_month = date(date_.year, date_.month, 1)
        _, first_day_week_of_year, _ = first_day_of_month.isocalendar()
        
        # If the first week of the month belongs to the previous year's last week (ISO standard behavior),
        # the simple subtraction needs adjustment. However, for a basic calculation:
        
        # This subtraction gives the difference in week numbers. Add 1 because we're 1-indexing the weeks.
        week_in_month = current_week_of_year - first_day_week_of_year + 1
        
        # Handle edge case where the current week of year is smaller than the first day's (e.g., year boundary)
        if week_in_month < 1:
            # This typically means the date belongs to the 'previous month's' partial week 
            # in the context of ISO week numbering, so we set it to 1.
            week_in_month = 1 

        print("Week of the month ==> ", week_in_month)
        return week_in_month
        

    def get(self, request):

        user = request.user
        now = timezone.now()

        # Parse filters
        try:
            month = int(request.query_params.get("month", now.month))
            year = int(request.query_params.get("year", now.year))
            week_number = request.query_params.get("week", None)
        except:
            month, year = now.month, now.year
            week_number = None

        # Get Store filter
        store_ids = request.query_params.getlist("store", [])
        stores = self._get_user_stores(user, store_IDs=store_ids)
        # print("stores", stores)
        print("Stores", stores.values_list("id"))

        # if not stores.exists():
        #     return CustomResponse(
        #         False,
        #         "No stores available for this user",
        #         403,
        #         {}
        #     )

        # --- Calculate Weekly Period ---
        print("Current Week Number ==> ", self._get_current_week())
        if week_number:
            # Specific week requested
            try:
                week_num = int(week_number)
                week_start, week_end = self._get_week_range(year, month, week_num)
            except:
                # Fallback to current accounting period
                week_start, week_end = self._get_week_range(year, month, self._get_current_week_month())
        else:
            # If no week number is specified, get the number of the current week
            # if multiple store is selected, use current week to get the week start and end dates
            current_week_number = self._get_current_week_month()
            print("Current week month", current_week_number)

            if stores.count() > 1:
                week_start, week_end = self._get_week_range(year, month, current_week_number)
            else:
                # If a single store, and no week is specified, the week start and week end of the account period
                # The accounting period is the time the last disbursement was made or the first purchase request 
                # was approved
                week_start = self._get_current_accounting_period(stores)
                week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        # --- Set date range for month ---
        start_month = timezone.make_aware(datetime(year, month, 1))
        end_month = (
            timezone.make_aware(datetime(year + 1, 1, 1)) - timedelta(days=1)
            if month == 12 else
            timezone.make_aware(datetime(year, month + 1, 1)) - timedelta(days=1)
        )

        # --- Calculate Imprest (Total Budget) ---
        # If single store selected, use that store's budget
        # If multiple stores, sum their budgets
        total_imprest = stores.aggregate(total_budget=Sum("budget"))["total_budget"] or Decimal(0)

        # --- Calculate Weekly Expenses ---
        # Only count APPROVED reimbursements in the current accounting period
        weekly_expenses = (
            Reimbursement.objects.filter(
                store__in=stores,
                status='approved',  # Only approved expenses
                created_at__range=[week_start, week_end]
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
        )

        # --- Calculate Weekly Balance ---
        weekly_balance = total_imprest - weekly_expenses

        # --- Validate Store Budget (for display purposes) ---
        # Check if any store has exceeded their individual budget
        # store_budget_warnings = []
        # for store in stores:
        #     store_expenses = (
        #         Reimbursement.objects.filter(
        #             store=store,
        #             status='approved',
        #             created_at__range=[week_start, week_end]
        #         ).aggregate(total=Sum("total_amount"))["total"] or Decimal(0)
        #     )
            
        #     if store_expenses > store.budget:
        #         store_budget_warnings.append({
        #             "store_id": store.id,
        #             "store_name": store.name,
        #             "budget": float(store.budget),
        #             "expenses": float(store_expenses),
        #             "exceeded_by": float(store_expenses - store.budget)
        #         })

        # --- Top 5 Purchases This Month ---
        top_monthly_purchases = list(
            ReimbursementItem.objects.filter(
                reimbursement__store__in=stores,
                reimbursement__status='approved',  # Only approved
                reimbursement__created_at__range=[start_month, end_month]
            ).values("item_name")
             .annotate(total_spent=Sum("item_total"))
             .order_by("-total_spent")[:5]
        )

        # --- Line Chart Data (Monthly Totals for Selected Year) ---
        line_qs = (
            Reimbursement.objects.filter(
                store__in=stores,
                status='approved',  # Only approved
                created_at__year=year
            )
            .annotate(month=ExtractMonth("created_at"))
            .values('month')
            .annotate(total=Sum('total_amount'))
            .order_by('month')
        )

        monthly_totals = {int(item["month"]): float(item["total"]) for item in line_qs}
        line_chart_data = [
            {
                "month": calendar.month_name[m],
                "total": monthly_totals.get(m, 0)
            }
            for m in range(1, 13)
        ]

        # --- Calculate available weeks in selected month ---
        # Determine how many weeks exist in the selected month
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        
        # Count Mondays in the month to determine number of weeks
        available_weeks = []
        current = first_day
        week_count = 1
        while current <= last_day:
            if current.weekday() == 0:  # Monday
                available_weeks.append(week_count)
                week_count += 1
            current += timedelta(days=1)
        
        if not available_weeks:  # Edge case: month starts on Tuesday or later
            available_weeks = [1]

        print("imprest amount", total_imprest)
        print("weekly expenses", weekly_expenses)
        print("weekly balance", weekly_balance)

        """
          {
                "role": user.role.name if user.role else None,
                "stores_count": stores.count(),
                "weekly_balance": float(weekly_balance),
                "weekly_expenses": float(weekly_expenses),
                "imprest_amount": float(budget),
                "top_monthly_purchases": top_monthly_purchases,
                "line_chart_data": line_chart_data,
            }
        """
        # --- Final Response ---
        return CustomResponse(
            True,
            "Dashboard data fetched successfully",
            200,
            {
                "role": user.role.name if user.role else None,
                "stores_count": stores.count(),
                # "selected_store": int(store_param) if store_param else None,
                # "selected_year": year,
                # "selected_month": month,
                # "selected_week": int(week_number) if week_number else None,
                # "available_weeks": available_weeks,
                "week_period": {
                    "start": week_start.strftime("%Y-%m-%d"),
                    "end": week_end.strftime("%Y-%m-%d")
                },
                "imprest_amount": float(total_imprest),
                "weekly_expenses": float(weekly_expenses),
                "weekly_balance": float(weekly_balance),
                # "budget_warnings": store_budget_warnings,  # Stores exceeding budget
                "top_monthly_purchases": top_monthly_purchases,
                "line_chart_data": line_chart_data,
            }
        )