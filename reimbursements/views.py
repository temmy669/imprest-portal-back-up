from collections import Counter
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import *
from .serializers import *
from utils.permissions import ViewReimbursementRequest, SubmitReimbursementRequest, ApproveReimbursementRequest, DeclineReimbursementRequest, DisburseReimbursementRequest
from helpers.response import CustomResponse
from users.auth import JWTAuthenticationFromCookie
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import FileSystemStorage
import os
from django.conf import settings
from django.utils import timezone


from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from collections import Counter
from datetime import datetime
from django.http import HttpResponse
import openpyxl
from openpyxl.utils import get_column_letter

class ReimbursementRequestView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated(), ViewReimbursementRequest()]
        elif self.request.method == 'POST':
            return [IsAuthenticated(), SubmitReimbursementRequest()]
        return [IsAuthenticated()]

    def get(self, request):
        user = request.user
        queryset = Reimbursement.objects.all()

        # Role-based restrictions
        if user.role.name == 'Restaurant Manager':
            queryset = queryset.filter(requester=user)
        elif user.role.name == 'Area Manager':
            queryset = queryset.filter(store__in=user.assigned_stores.all())
        elif user.role.name == 'Internal Control':
            queryset = queryset.filter(status='approved')
        elif user.role.name == 'Treasurer':
            queryset = queryset.filter(internal_control_status='approved')
            

        
         # Filters from query params
        area_manager_id = request.query_params.get("area_manager")
        store_ids = request.query_params.getlist("stores")  
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")
        search = request.query_params.get("search")
        search_query = request.query_params.get("q", "").strip()
        region_id = request.query_params.get("region")


        # Area Manager filter
        if area_manager_id:
           queryset = queryset.filter(store__assigned_users__id=area_manager_id)
                             

        # Store filter
        if store_ids:
            queryset = queryset.filter(store_id__in=store_ids)
            
        # Region Filter
        if region_id:
            queryset = queryset.filter(store__region_id=region_id)       

        # Date range filter
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

        # Status filter
        if status:
            queryset = queryset.filter(status=status)

        # Search filter (by requester name)
        if search:
            queryset = queryset.filter(
                Q(requester__first_name__icontains=search) |
                Q(requester__last_name__icontains=search) |
                Q(requester__name__icontains=search)  
            )
        
        # Special RR-XXXX search (takes priority if provided)
        if search_query:
            if search_query.upper().startswith("RR-"):
                try:
                    request_id = int(search_query.upper().replace("RR-", ""))
                    queryset = queryset.filter(id=request_id)
                except ValueError:
                    return CustomResponse(False, "Invalid request ID format. Expected RR-XXXX", 400)
            else:
                return CustomResponse(False, "Only RR-XXXX search is supported in 'q'", 400)


        # Pagination
        paginator = PageNumberPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)

        # Calculate status counts for just this page
        if user.role.name == 'Treasurer':
            status_list = [obj.disbursement_status for obj in (paginated_queryset or [])]
            
        elif user.role.name == 'Internal Control':
            status_list = [obj.internal_control_status for obj in (paginated_queryset or [])]  
            
        else:
            status_list = [obj.status for obj in (paginated_queryset or [])]
        
        status_count_dict = dict(Counter(status_list))
        
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
            }
        )

    def post(self, request):
        # Step 1: Create reimbursement (draft by default)
        serializer = ReimbursementSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return CustomResponse(False, "Invalid data", 400, serializer.errors)

        reimbursement = serializer.save(requester=request.user)

        return CustomResponse(
            True,
            "Reimbursement submitted for approval",
            201,
            ReimbursementSerializer(reimbursement).data
        )
        
        

    def put(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        serializer = ReimbursementUpdateSerializer(
            reimbursement, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "Reimbursement Request Updated Successfully", 200, serializer.data)
        return CustomResponse(False, serializer.errors, 400)



class UploadReceiptView(APIView):
    """
    Upload a receipt for a single reimbursement item.
    POST /reimbursement-items/<int:item_id>/receipt/
    form-data: receipt=<file>
    """
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, item_id):
        item = get_object_or_404(
            ReimbursementItem,
            pk=item_id,
            reimbursement__requester=request.user  # ensure ownership
        )

        if "receipt" not in request.FILES:
            return CustomResponse(False, "No file uploaded", 400)

        receipt_file = request.FILES["receipt"]

        # Save using the model FileField's storage (upload_to='receipts/')
        # This is the simplest and most robust way.
        item.receipt.save(receipt_file.name, receipt_file, save=True)

        return CustomResponse(
            True,
            "Receipt uploaded successfully",
            200,
        )
        
    
class ApproveReimbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]
    
    # Approve a reimbursement request and its items
    def post(self, request, pk):
        reimbursement = get_object_or_404(Reimbursement, pk=pk)
        
        name = "" #place holder for user role name to be used in response message
        
        if request.user.role.name == "Area Manager":
            if reimbursement.status != 'pending':
                return CustomResponse(False, "Reimbursement is not pending", 400)
            
            reimbursement.status = 'approved'
            reimbursement.area_manager = request.user
            reimbursement.area_manager_approved_at = timezone.now()
            
            # Update all items status to approved
            reimbursement.items.update(status="approved")
            name = "Area Manager"
            
        elif request.user.role.name == "Internal Control":
            if reimbursement.internal_control_status != 'pending':
                return CustomResponse(False, "Reimbursement is not pending", 400)
            
            reimbursement.internal_control_status = "approved"
            reimbursement.internal_control = request.user
            reimbursement.internal_control_approved_at = timezone.now()
            
             # Update all items status to approved
            reimbursement.items.update(internal_control_status="approved")
            name = "Internal Control"
        
        reimbursement.updated_by = request.user
        reimbursement.save(user=request.user)
       
        
        message = f"Reimbursement approved by {name} successfully"

        return CustomResponse(True, message, 200)
    

class ApproveReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ApproveReimbursementRequest]
    
    #Approve items in a reimbursement request
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)
        items = re.items.all()
        
        # Object-level permission check
        self.check_object_permissions(request, re)
        
        if request.user.role.name == "Area Manager":
            if item.status == 'approved':
                return CustomResponse(False, 'Item is already approved.', 400)
            
            item.status = 'approved'
            item.save()

            #check if any item is declined
            if any(i.status == 'declined' and i.status != 'pending' for i in items):
                re.status = 'declined'
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
            
            # Check if all items are approved
            elif all(i.status == 'approved' for i in items):
                re.status = 'approved'
                re.area_manager = request.user
                re.area_manager_approved_at = timezone.now()
        
        elif request.user.role.name == "Internal Control":
            if item.internal_control_status == 'approved':
                return CustomResponse(False, 'Item is already approved.', 400)

            item.internal_control_status = 'approved'
            item.save()
            
            if any(i.internal_control_status == 'declined' and i.internal_control_status != 'pending' for i in items):
                re.internal_control_status = "declined"
                re.status = "pending"  # IC decline → send back as pending
                item.status = 'pending'
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()
            
            elif all(i.internal_control_status == 'approved' for i in items):
                re.internal_control_status = "approved"
                re.internal_control = request.user
                re.internal_control_approved_at = timezone.now()
        re.save(user=request.user)

        return CustomResponse(True,
            {
                'status': re.status,
                'internal_control_status': re.internal_control_status,
                'item_id': item.id
            },
            200
        )
        
        
class DeclineReimbursementView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk):
        re = get_object_or_404(Reimbursement, pk=pk)
        items = re.items.all()
        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)

        if request.user.role.name == "Internal Control":
            re.internal_control_status = "declined"
            # Send back to Area Manager as pending
            re.status = "pending"
            items.update(status="pending") # Reset all items to pending
            re.internal_control = request.user
            re.internal_control_declined_at = timezone.now()
            
            # Update all items status to declined
            re.items.update(internal_control_status="declined")
            
        elif request.user.role.name == "Area Manager":
            # Final decline
            re.status = "declined"
            re.area_manager = request.user
            re.area_manager_declined_at = timezone.now()
            # Update all items status to declined
            re.items.update(status="declined") 
        re.save(user=request.user)

        # Create decline comment
        ReimbursementComment.objects.create(
            reimbursement=re,
            author=request.user,
            text=comment_text
        )

        return CustomResponse(
            True,
            {"status": re.status, "comment": comment_text, "internal_control_status": re.internal_control_status},
            200
        )


class DeclineReimbursementItemView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, DeclineReimbursementRequest]
    
    def post(self, request, pk, item_id):
        re = get_object_or_404(Reimbursement, pk=pk)
        item = get_object_or_404(ReimbursementItem, pk=item_id, reimbursement=re)
        items = re.items.all()

        self.check_object_permissions(request, re)

        comment_text = request.data.get('comment', '').strip()
        if not comment_text:
            return CustomResponse(False, 'Comment is required when declining', 400)
        
        if request.user.role.name == "Area Manager":
            if item.status == 'declined':
                return CustomResponse(False, "Item is already declined", 400)
            
            # Decline this item
            item.status = 'declined'
            item.save()
            
            if any(i.status == 'pending' for i in items):
            # Some items still pending → request remains pending
                re.status = "pending"
            elif all(i.status != 'pending' for i in items):
            # No more pending items
                re.status = "declined"
                re.area_manager = request.user
                re.area_manager_declined_at = timezone.now()
            
        elif request.user.role.name == "Internal Control":
            if item.internal_control_status == 'declined':
                return CustomResponse(False, "Item is already declined", 400)
            
            # Decline this item
            item.internal_control_status = "declined"
            item.save()
            
            if any(i.internal_control_status == 'pending' for i in items):
                # Some items still pending → request remains pending
                re.internal_control_status = "pending"
                
            elif all(i.internal_control_status != 'pending' for i in items):
                # IC decline → send back as pending
                re.status = "pending"
                re.internal_control_status = "declined"
                re.internal_control = request.user
                re.internal_control_declined_at = timezone.now()    
        re.save(user=request.user)

        # Save comment
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
                "item_id": item.id,
                "comment": comment_text
            },
            200
        )
        
class ExportReimbursement(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ViewReimbursementRequest]

    def get(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        status = request.query_params.get("status")

        user = request.user
        reimbursement = Reimbursement.objects.all()

        # validate inputs
        if not start_date or not end_date or not status:
            return CustomResponse(False, "start_date, end_date and status are required", 400)

        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return CustomResponse(False, "Invalid date format. Use YYYY-MM-DD", 400)

        if start_date > end_date:
            return CustomResponse(False, "start_date cannot be after end_date", 400)

        # role-based queryset
        if user.role.name == "Area Manager":
            queryset = reimbursement.filter(
                store__in=user.assigned_stores.all(),
                created_at__date__gte=start_date.date(),
                created_at__date__lte=end_date.date(),
                status__iexact=status,
            )
            headers = ["Request ID", "Requester", "Store", "Total Amount", "Status", "Date Created"]
            file_name = f"AM_reimbursement_requests_{start_date.date()}_{end_date.date()}.xlsx"

        elif user.role.name == "Internal Control":
            queryset = reimbursement.filter(
                status="approved",
                created_at__date__gte=start_date.date(),
                created_at__date__lte=end_date.date(),
                internal_control_status__iexact=status,
            )
            headers = ["Request ID", "Requester", "Store", "Total Amount", "Status", "Date Created"]
            file_name = f"IC_reimbursement_requests_{start_date.date()}_{end_date.date()}.xlsx"

        elif user.role.name == "Treasurer":
            queryset = reimbursement.filter(
                internal_control_status="approved",
                created_at__date__gte=start_date.date(),
                created_at__date__lte=end_date.date(),
                disbursement_status__iexact=status,
            )
            headers = [
                "Request ID",
                "Requester",
                "Region",
                "Store",
                "Area Manager",
                "Total Amount",
                "Status",
                "Date Created",
                "Bank Name",
                "Account Name",
            ]
            file_name = f"Treasury_reimbursement_requests_{start_date.date()}_{end_date.date()}.xlsx"

        elif user.role.name == "Restaurant Manager":
            queryset = reimbursement.filter(
                requester=user,
                created_at__date__gte=start_date.date(),
                created_at__date__lte=end_date.date(),
                status__iexact=status,
            )
            headers = ["Request ID", "Store", "Total Amount", "Status", "Date Created"]
            file_name = f"RM_reimbursement_requests_{start_date.date()}_{end_date.date()}.xlsx"

        else:
            return CustomResponse(False, "You are not allowed to export reimbursements", 403)

        # workbook
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = f"RRs {start_date:%d-%m} to {end_date:%d-%m}"
        sheet.append(headers)

        # rows
        for rr in queryset:
            if user.role.name == "Internal Control":
                row = [
                    f"RR-{rr.id:04d}",
                    f"{rr.requester.first_name} {rr.requester.last_name}",
                    rr.store.name if rr.store else "",
                    rr.total_amount, 
                    rr.internal_control_status.capitalize(),
                    rr.created_at.strftime("%Y-%m-%d")
                ]

            elif user.role.name == "Treasurer":
                row = [
                    f"RR-{rr.id:04d}",
                    f"{rr.requester.first_name} {rr.requester.last_name}",
                    rr.store.region.name if rr.store and rr.store.region else "",
                    rr.store.name if rr.store else "",
                    f"{rr.store.area_manager.first_name} {rr.store.area_manager.last_name}"
                    if rr.store and rr.store.area_manager
                    else "",
                    rr.total_amount,
                    rr.disbursement_status.capitalize(),
                    rr.created_at.strftime("%Y-%m-%d"),
                    rr.bank.bank_name if rr.bank else "",
                    rr.account.account_name if rr.account else "",
                ]

            elif user.role.name == "Area Manager":
                row = [
                    f"RR-{rr.id:04d}",
                    f"{rr.requester.first_name} {rr.requester.last_name}",
                    rr.store.name if rr.store else "",
                    rr.total_amount,
                    rr.status.capitalize(),
                    rr.created_at.strftime("%Y-%m-%d"),
                ]

            else:  # Restaurant Manager
                row = [
                    f"RR-{rr.id:04d}",
                    rr.store.name if rr.store else "",
                    rr.total_amount,
                    rr.status.capitalize(),
                    rr.created_at.strftime("%Y-%m-%d"),
                ]

            sheet.append(row)

        # auto column widths
        for col in sheet.columns:
            max_length = max((len(str(cell.value)) for cell in col if cell.value), default=0)
            sheet.column_dimensions[col[0].column_letter].width = max_length + 2

        # build response
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        workbook.save(response)
        return response


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
    
        