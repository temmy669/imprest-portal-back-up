from collections import Counter
from rest_framework.generics import get_object_or_404
from utils.pagination import DynamicPageSizePagination
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import *
from .serializers import *
from purchases.models import PurchaseRequest, LimitConfig, PurchaseRequestItem
from utils.permissions import (ViewReimbursementRequest,
                               SubmitReimbursementRequest,
                               ApproveReimbursementRequest,
                               DeclineReimbursementRequest,
                               ChangeReimbursementRequest,
                                DisburseReimbursementRequest)
from helpers.response import CustomResponse
from users.auth import JWTAuthenticationFromCookie
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
import os
from django.conf import settings
from django.utils import timezone
from decimal import InvalidOperation, Decimal

from django.core.files.storage import FileSystemStorage
from rest_framework.parsers import MultiPartParser, FormParser

from django.db.models import Q, Count, Sum
from collections import Counter
from drf_spectacular.utils import extend_schema, OpenApiParameter
from datetime import datetime
from django.http import HttpResponse
import openpyxl
from openpyxl.utils import get_column_letter

import cloudinary
import cloudinary.uploader
import re
from utils.receipt_validation import validate_receipt
from django.db import transaction
from utils.email_utils import send_reimbursement_rejection_notification, send_reimbursement_approval_notification


class ReimbursementRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), ViewReimbursementRequest()]
        elif self.request.method == 'POST':
            return [IsAuthenticated(), SubmitReimbursementRequest()]
        elif self.request.method == 'PUT':
            return [IsAuthenticated(), ChangeReimbursementRequest()]
        return [IsAuthenticated()]

    def get(self, request):
        user = request.user
        queryset = Reimbursement.objects.all().order_by('-created_at')

        # Get filters
        area_manager_ids = request.query_params.getlist("area_manager")
        store_ids = request.query_params.getlist("stores")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")
        internal_control_status = request.query_params.get("internal_control_status")
        search = request.query_params.get("search")
        search_query = request.query_params.get("q", "").strip()
        region_id = request.query_params.get("region")
        disbursement_status = request.query_params.get("disbursement_status")

        # Role-based access
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(store_id=user.store_id)
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__in=user.assigned_stores.all())
        elif user.role.name == 'Internal Control':
            queryset = queryset.filter(Q(status__in=['approved', 'pending']) & Q( Q(internal_control=user)| Q(internal_control__isnull=True) ))
        elif user.role.name == 'Treasurer':
            queryset = queryset.filter(internal_control_status='approved')
        
        # Determine which field represents status for the user role
        if user.role.name == 'Treasurer':
            status_field = 'disbursement_status'
        elif user.role.name == 'Internal Control':
            status_field = 'internal_control_status'
        else:
            status_field = 'status'

        # Keep a base queryset for status count BEFORE applying query param filters
        base_queryset_for_status_count = queryset
        status_filter = False
        # Calculate status counts across all statuses BEFORE query param filters
        # status_counts_all = (
        #     base_queryset_for_status_count
        #     .values(status_field)
        #     .annotate(count=Count(status_field))
        #     .order_by()
        # )
        # print("Status count all ==> ", status_counts_all)
        # status_count_dict = {item[status_field]: item["count"] for item in status_counts_all}

        # --- Now apply filters ---
        if area_manager_ids:
            queryset = queryset.filter(store__area_manager__id__in=area_manager_ids)

        if disbursement_status:
            queryset = queryset.filter(disbursement_status=disbursement_status)

        if store_ids:
            queryset = queryset.filter(store_id__in=store_ids)

        if region_id:
            queryset = queryset.filter(store__region_id=region_id)

        if start_date:
            try:
                queryset = queryset.filter(created_at__date__gte=datetime.strptime(start_date, "%Y-%m-%d").date())
            except ValueError:
                pass

        if end_date:
            try:
                queryset = queryset.filter(created_at__date__lte=datetime.strptime(end_date, "%Y-%m-%d").date())
            except ValueError:
                pass

        if status:
            queryset = queryset.filter(status=status)
        
        if internal_control_status:
            queryset = queryset.filter(
                internal_control_status=internal_control_status)
            
        if search:
            queryset = queryset.filter(
                Q(requester__first_name__icontains=search) |
                Q(requester__last_name__icontains=search)
            )

        if search_query:
            if search_query.upper().startswith("RR-"):
                try:
                    request_id = int(search_query.upper().replace("RR-", ""))
                    queryset = queryset.filter(id=request_id)
                except ValueError:
                    return CustomResponse(False, "Invalid request ID format. Expected RR-XXXX", 400)
            else:
                return CustomResponse(False, "Only RR-XXXX search is supported in 'q'", 400)
        
    
        # #return empty status count if queryset is empty after filters
        # if not queryset.exists():
        #     status_count_dict = {}
        
        # STATUS COUNT
        status_counts_all = (
            base_queryset_for_status_count
            .values(status_field)
            .annotate(count=Count(status_field))
            .order_by()
        )

        print("Status count all ==> ", status_counts_all)
        status_count_dict = {item[status_field]: item["count"] for item in status_counts_all}
        
        # --- Pagination and serialization ---
        paginator = DynamicPageSizePagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = ReimbursementSerializer(paginated_queryset, many=True)

        return CustomResponse(
            True,
            "Filtered reimbursement requests retrieved",
            200,
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
                "status_counts": status_count_dict, 
            },
        )
        

    def post(self, request):
        # Step 1: Create reimbursement (draft by default)
        print("Request Data ==> ", request.data)
        try:
            serializer = ReimbursementSerializer(data=request.data, context={'request': request})
            if not serializer.is_valid():
                errors = serializer.errors
                # Try to extract a meaningful message
                message = "Invalid data"
                if isinstance(errors, dict):
                    if 'detail' in errors:
                        message = errors['detail']

                    else:
                        first_key = next(iter(errors))
                        first_error = errors[first_key]
                        if isinstance(first_error, list):
                            message = first_error[0]
                        else:
                            message = first_error

                return CustomResponse(
                    False,
                    message,
                    400,
                    None
                )
            
            reimbursement = serializer.save(requester=request.user)

            # Update the related purchase request with the newly created reimbursement id
            purchase_request_refs = set()

            for item in reimbursement.items.all():
                ref = (item.purchase_request_ref or "").strip()
                match = re.match(r'^PR-0*(\d+)', ref)  # handles cases like PR-0015 or PR-0015-12000.00
                if match:
                    pr_id = int(match.group(1))  # convert to int (15)
                    print(pr_id)
                    purchase_request_refs.add(pr_id)

            if purchase_request_refs:
                purchase_requests = PurchaseRequest.objects.filter(id__in=purchase_request_refs)
                purchase_requests.update(reimbursement=reimbursement)
            
        # Sync receipt_validated from purchase request items to reimbursement items
            for item in reimbursement.items.all():
                pr_item_ref = (item.purchase_request_ref or "").strip()
                match = re.match(r'^PR-0*(\d+)', pr_item_ref)

                if not match:
                    continue

                pr_id = int(match.group(1))

                pr_item = (
                    PurchaseRequestItem.objects
                    .filter(
                        request_id=pr_id,
                    )
                    .order_by('-id')
                    .first()
                )

                if not pr_item:
                    continue

                item.receipt_validated = pr_item.receipt_validated
                item.save(update_fields=['receipt_validated'])

            return CustomResponse(
                True,
                "Reimbursement submitted for approval",
                201,
                ReimbursementSerializer(reimbursement).data
            )
        
        except Exception as err:
            return CustomResponse(
                False,
                "Unable to create reimbursement",
                400,
                {
                    "error":str(err)
                }
            )
        
        

    def put(self, request, pk, item_id=None):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        serializer = ReimbursementUpdateSerializer(
            reimbursement, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            print(serializer.is_valid())
            serializer.save()
            return CustomResponse(True, "Reimbursement Request Updated Successfully", 200, serializer.data)
        return CustomResponse(False, serializer.errors, 400)


class UploadReceiptView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, SubmitReimbursementRequest]

    def post(self, request):
        if 'receipt' not in request.FILES:
            return CustomResponse(False, "No receipt file provided.", 400)
        receipt_file = request.FILES['receipt']

        item_id = request.data.get('item_id')
        if not item_id:
            return CustomResponse(False, "Item ID is required for validation.", 400)

        try:
            item = PurchaseRequestItem.objects.get(id=item_id)
        except PurchaseRequestItem.DoesNotExist:
            return CustomResponse(False, "Invalid item ID.", 400)
        
        # Check if receipt already validated and uploaded
        if item.receipt_validated:
            return CustomResponse(
                False, 
                "Receipt has already been uploaded and validated for this item.", 
                400,
                {
                    "receipt_no": item.receipt_no,
                    "extracted_vendor": item.extracted_vendor
                }
            )

        # Read the file content for validation
        receipt_data = receipt_file.read()
        
        # Validate the receipt BEFORE uploading
        validation_result = validate_receipt(
            receipt_data, 
            item.total_price, 
            item.request.created_at.date() if item.request.created_at else None
        )

        # # Check validation result BEFORE uploading
        # if not validation_result['validated']:
        #     return CustomResponse(
        #         False, 
        #         "Receipt validation failed.", 
        #         400, 
        #         {"validation_errors": validation_result['errors']}
        #     )

        # Only upload if validation passed
        # Need to reset file pointer since we already read it
        receipt_file.seek(0)
        
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(receipt_file, folder="receipts/")
            receipt_url = result.get("secure_url")
        else:
            # Local storage
            fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'receipts/'))
            filename = fs.save(f"receipts/{receipt_file.name}", receipt_file)
            receipt_url = fs.url(filename)

        # Save validation data to item (only reached if validation passed)
        item.receipt_validated = True
        item.receipt_no = validation_result.get('receipt_number')
        item.extracted_amount = validation_result.get('extracted_amount')
        item.extracted_date = validation_result.get('extracted_date')
        item.extracted_vendor = validation_result.get('extracted_vendor')
        item.validation_errors = None
        item.save()

        return CustomResponse(
            True, 
            "Receipt uploaded and validated successfully.", 
            200, 
            {"receipt_url": receipt_url}
        )
    
class ApproveReimbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]

    def post(self, request, pk):
       with transaction.atomic(): 
            reimbursement = get_object_or_404(Reimbursement, pk=pk)
            # self.check_object_permissions(request, reimbursement)
            role = request.user.role.name
            print("role", role)
            if role == "Area Manager":
                if reimbursement.status != "pending":
                    return CustomResponse(False, "Reimbursement is not pending", 400)

                reimbursement.status = "approved"
                reimbursement.area_manager = request.user
                reimbursement.area_manager_approved_at = timezone.now()
                reimbursement.items.update(status="approved")

            elif role == "Internal Control":
                if reimbursement.internal_control_status != "pending":
                    return CustomResponse(False, "Reimbursement is not pending", 400)

                reimbursement.internal_control_status = "approved"
                reimbursement.internal_control = request.user
                reimbursement.internal_control_approved_at = timezone.now()
                reimbursement.items.update(internal_control_status="approved")

            else:
                return CustomResponse(False, "Invalid role", 403)

            reimbursement.updated_by = request.user
            reimbursement.save(user=request.user)

            # send_reimbursement_approval_notification(
            #     reimbursement,
            #     request.user
            # )

            return CustomResponse(
                True,
                f"Reimbursement approved by {role} successfully",
                200
            )


class ApproveReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]

    def post(self, request, pk, item_id):
        with transaction.atomic():
            re = get_object_or_404(Reimbursement, pk=pk)
            item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)
            items = re.items.all()

            self.check_object_permissions(request, re)

            role = request.user.role.name
            approved_now = False  # track if approval just completed

            if role == "Area Manager":
                if item.status == "approved":
                    return CustomResponse(False, "Item already approved", 400)

                item.status = "approved"
                item.save()

                if all(i.status == "approved" for i in items):
                    re.status = "approved"
                    re.area_manager = request.user
                    re.area_manager_approved_at = timezone.now()
                    approved_now = True

            elif role == "Internal Control":
                if item.internal_control_status == "approved":
                    return CustomResponse(False, "Item already approved", 400)

                item.internal_control_status = "approved"
                item.save()
                
                #Build item from reimbursements data to complete byd structure

                if all(i.internal_control_status == "approved" for i in items):
                    re.internal_control_status = "approved"
                    re.internal_control = request.user
                    re.internal_control_approved_at = timezone.now()
                    approved_now = True

            else:
                return CustomResponse(False, "Invalid role", 403)

            re.updated_by = request.user
            re.save(user=request.user)

            # SEND EMAIL ONLY WHEN FULL APPROVAL JUST HAPPENED
            if approved_now:
                send_reimbursement_approval_notification(
                    re,
                    request.user
                )

            return CustomResponse(
                True,
                {
                    "status": re.status,
                    "internal_control_status": re.internal_control_status,
                    "item_id": item.id
                },
                200
            )


class DeclineReimbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]

    def post(self, request, pk):
        comment_text = request.data.get("comment", "").strip()
        if not comment_text:
            return CustomResponse(False, "Comment is required when declining", 400)

        with transaction.atomic():
            re = (
                Reimbursement.objects
                .select_for_update()
                .get(pk=pk)
            )

            items = re.items.select_for_update().all()

            self.check_object_permissions(request, re)
            user_role = request.user.role.name

            # -------- INTERNAL CONTROL DECLINE --------
            if user_role == "Internal Control":
                re.internal_control_status = "declined"
                re.status = "pending"
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()

                items.update(
                    status="pending",
                    internal_control_status="declined"
                )

                re.save(user=request.user)
                send_reimbursement_rejection_notification(
                    re, request.user, comment_text
                )
            # -------- AREA MANAGER FINAL DECLINE --------
            elif user_role == "Area Manager":
                re.status = "declined"
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
                items.update(status="declined")
                re.save(user=request.user)
                send_reimbursement_rejection_notification(
                    re, request.user, comment_text
                )

            else:
                return CustomResponse(False, "Invalid role", 403)

            ReimbursementComment.objects.create(
                reimbursement=re,
                author=request.user,
                text=comment_text
            )

        return CustomResponse(
            True,
            {
                "status": re.status,
                "internal_control_status": re.internal_control_status,
                "comment": comment_text
            },
            200
        )

class DeclineReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]

    def post(self, request, pk, item_id):
        comment_text = request.data.get("comment", "").strip()
        if not comment_text:
            return CustomResponse(False, "Comment is required", 400)

        with transaction.atomic():
            re = (
                Reimbursement.objects
                .select_for_update()
                .get(pk=pk)
            )

            item = (
                ReimbursementItem.objects
                .select_for_update()
                .get(pk=item_id, reimbursement=re)
            )

            self.check_object_permissions(request, re)

            # ---- AREA MANAGER FLOW ----
            if request.user.role.name == "Area Manager":
                if item.status == "declined":
                    return CustomResponse(False, "Item already declined", 400)

                item.status = "declined"
                item.save()

                items = re.items.all()

                if items.filter(status="pending").exists():
                    re.status = "pending"
                else:
                    re.status = "declined"
                    re.area_manager = request.user
                    re.area_manager_declined_at = timezone.now()

                re.save(user=request.user)

                # Send email ONLY if final decline
                if re.status == "declined":
                    send_reimbursement_rejection_notification(
                        re, request.user, comment_text
                    )

            # ---- INTERNAL CONTROL FLOW ----
            elif request.user.role.name == "Internal Control":
                if item.internal_control_status == "declined":
                    return CustomResponse(False, "Item already declined", 400)

                item.internal_control_status = "declined"
                item.save()

                items = re.items.all()

                if items.filter(internal_control_status="pending").exists():
                    re.internal_control_status = "pending"
                else:
                    re.internal_control_status = "declined"
                    re.status = "pending"
                    re.internal_control = request.user
                    re.internal_control_declined_at = timezone.now()

                re.save(user=request.user)

                send_reimbursement_rejection_notification(
                    re, request.user, comment_text
                )

            ReimbursementComment.objects.create(
                reimbursement=re,
                author=request.user,
                text=comment_text
            )

        return CustomResponse(True, {
            "status": re.status,
            "item_id": item.id
        }, 200)
    
class ExportReimbursement(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewReimbursementRequest]
    
    # -------------------------------
    # Helpers
    # -------------------------------
    #Helper methods called by the export view
    def get_queryset(self, user, start_date, end_date, status):
        qs = Reimbursement.objects.all()

        if user.role.name == "Area Manager":
            return qs.filter(
                store__in=user.assigned_stores.all(),
                created_at__date__range=(start_date, end_date),
                status__iexact=status,
            )

        if user.role.name == "Internal Control":
            return qs.filter(
                status="approved",
                created_at__date__range=(start_date, end_date),
                internal_control_status__iexact=status,
            )

        if user.role.name == "Treasurer":
            return qs.filter(
                internal_control_status="approved",
                created_at__date__range=(start_date, end_date),
                disbursement_status__iexact=status,
            )

        if user.role.name == "Restaurant Manager":
            return qs.filter(
                requester=user,
                created_at__date__range=(start_date, end_date),
                status__iexact=status,
            )

        return None

    def export_internal_control(self, queryset, start_date, end_date):
        from collections import defaultdict
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Internal Control"

        expense_types = sorted({
            item.item_name
            for rr in queryset
            for item in rr.items.all()
        })

        headers = ["Staff Name"] + expense_types + ["Total"]
        sheet.append(headers)

        data = defaultdict(lambda: defaultdict(Decimal))

        for rr in queryset:
            name = f"{rr.requester.first_name} {rr.requester.last_name}"

            for item in rr.items.all():
                data[name][item.item_name] += item.item_total

            data[name]["Total"] += rr.total_amount

        for name, expenses in data.items():
            row = [name] + [expenses.get(h, 0) for h in expense_types] + [expenses["Total"]]
            sheet.append(row)

        return self.build_response(
            workbook,
            f"IC_reimbursements_{start_date.date()}_{end_date.date()}.xlsx"
        )

    def export_treasury(self, queryset, start_date, end_date):
        from collections import defaultdict
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Treasury"

        headers = ["Store", "Region", "Total Amount"]
        sheet.append(headers)

        stores = defaultdict(lambda: {"region": "", "total": 0})

        for rr in queryset:
            store = rr.store.name
            stores[store]["region"] = rr.store.region.name if rr.store.region else ""
            stores[store]["total"] += rr.total_amount

        for store, data in stores.items():
            sheet.append([store, data["region"], data["total"]])

        return self.build_response(
            workbook,
            f"Treasury_reimbursements_{start_date.date()}_{end_date.date()}.xlsx"
        )


    def export_default(self, queryset, user, start_date, end_date):
        workbook = openpyxl.Workbook()
        sheet = workbook.active

        headers = ["Request ID", "Requester", "Store", "Total", "Status", "Date"]
        sheet.append(headers)

        for rr in queryset:
            sheet.append([
                f"RR-{rr.id:04d}",
                f"{rr.requester.first_name} {rr.requester.last_name}",
                rr.store.name if rr.store else "",
                rr.total_amount,
                rr.status.capitalize(),
                rr.created_at.strftime("%Y-%m-%d")
            ])

        return self.build_response(
            workbook,
            f"reimbursements_{start_date.date()}_{end_date.date()}.xlsx"
        )


    def build_response(self, workbook, filename):
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        workbook.save(response)
        return response

    #-------------------------------
    # Main GET method for export
    #-------------------------------    
     
    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")
        # template = request.query_params.get("template") # e.g., "internal_control", "treasury", etc.

        user = request.user

        if not start_date or not end_date or not status:
            return CustomResponse(False, "start_date, end_date and status are required", 400)

        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return CustomResponse(False, "Invalid date format. Use YYYY-MM-DD", 400)

        if start_date > end_date:
            return CustomResponse(False, "start_date cannot be after end_date", 400)

        queryset = self.get_queryset(user, start_date, end_date, status)
        if queryset is None:
            return CustomResponse(False, "You are not allowed to export reimbursements", 403)

        if user.role.name == "Internal Control":
            return self.export_internal_control(queryset, start_date, end_date)

        if user.role.name == "Treasurer":
            return self.export_treasury(queryset, start_date, end_date)

        return self.export_default(queryset, user, start_date, end_date)




class DisbursemntView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DisburseReimbursementRequest]
    
    # Disburse a reimbursement request and its items
    def post(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        
        if reimbursement.disbursement_status != 'pending':
            return CustomResponse(False, "The selected reimbursement is not a pending disbursement", 400)
        
        reimbursement.disbursement_status = 'disbursed'
        reimbursement.treasurer = request.user
        bank_id = request.data.get('bank')
        account_id = request.data.get('account')
        reimbursement.bank = get_object_or_404(Bank, id=bank_id)
        reimbursement.account = get_object_or_404(Account, id=account_id)
        reimbursement.disbursed_at = timezone.now()
           
            
        reimbursement.updated_by = request.user
        reimbursement.save(user=request.user)
       
        
        message = f"Reimbursement disbursed by Treasurer successfully"

        return CustomResponse(True, message, 200)
    
class BulkDisbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DisburseReimbursementRequest]
    
    # Bulk Disburse reimbursement requests and their items
    #ids refers to id of the selected reimbursement requests
    def post(self, request):
        ids = request.data.get('reimbursement_ids', [])
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return CustomResponse(False, "Invalid 'ids' format. Must be a list of integers.", 400)
        
        
        
        reimbursements = Reimbursement.objects.filter(id__in=ids)
        updated_count = 0
        
        for reimbursement in reimbursements:
            if reimbursement.disbursement_status != 'pending':
                continue  # skip non-pending disbursements
            reimbursement.disbursement_status = 'disbursed'
            reimbursement.treasurer = request.user
            bank_id = request.data.get('bank')
            account_id = request.data.get('account')
            reimbursement.bank = get_object_or_404(Bank, id=bank_id)
            reimbursement.account = get_object_or_404(Account, id=account_id)
            reimbursement.disbursed_at = timezone.now()
            reimbursement.updated_by = request.user
            reimbursement.save(user=request.user)
            updated_count += 1
        
        return CustomResponse(True, f"{updated_count} reimbursement(s) disbursed successfully", 200)
    
    
