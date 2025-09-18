from rest_framework.permissions import BasePermission, SAFE_METHODS
from purchases.models import PurchaseRequest, LimitConfig
from reimbursements.models import Reimbursement
from helpers.exceptions import CustomValidationException

purchase_limit = LimitConfig.objects.first()


class BaseRolePermission(BasePermission):
    """
    Base permission class that all other permissions will inherit from
    """
    codename = None
    amount_threshold = None
    object_permission = False
    

    def has_permission(self, request, view):
        user = request.user
        
        # Block inactive users immediately
        if not getattr(user, 'is_active', False):
            raise CustomValidationException("Your account is not active. Please contact your administrator.")
            return False

        # Admins and Superusers always allowed
        if getattr(user, 'is_superuser', False) or getattr(user.role, 'name', None) == 'Admin':
            return True

        # Amount-based logic (if defined)
        if self.amount_threshold is not None:
            amount = self.get_amount_from_request(request, view)
            if amount is None:
                return False

            if amount >= self.amount_threshold:
                return user.role.permissions.filter(codename='approve_over_limit').exists()
            return True

        # Codename-based check
        if self.codename:
            return user.role.permissions.filter(codename=self.codename).exists()

        return False

    def get_amount_from_request(self, request, view):
        try:
            return float(request.data.get('amount'))
        except (ValueError, TypeError):
            return None
    
    def has_object_permission(self, request, view, obj):
        if not self.object_permission:
            return True

        user = request.user

        # Admins/superusers bypass
        if getattr(user, 'is_superuser', False) or getattr(user.role, 'name', None) == 'Admin':
            return True

        # --- PurchaseRequest logic ---
        if isinstance(obj, PurchaseRequest):
            if self.codename == 'change_purchase_request':
                return obj.requester == user
            elif self.codename in [
                'approve_purchase_request',
                'decline_purchase_request',
                'view_purchase_request',
            ]:
                return (
                    getattr(user.role, 'name', '') == 'Area Manager' and
                    obj.store in user.assigned_stores.all()
                )

        # --- Reimbursement logic ---
        if isinstance(obj, Reimbursement):
            role = getattr(user.role, 'name', '')

            if self.codename == 'submit_reimbursement_request':
                return obj.requester == user

            elif self.codename in [
                'approve_reimbursement_request',
                'decline_reimbursement_request',
                'view_reimbursement_request',
            ]:
                return (
                    (role == 'Area Manager' and obj.store in user.assigned_stores.all())
                    or role == 'Internal Control'
                )

            elif self.codename == 'disburse_reimbursement':
                return role == 'Treasurer'

    
class IsSuperUserOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_superuser

# Specific permission classes for each use case
class SubmitPurchaseRequest(BaseRolePermission):
    codename = 'submit_purchase_request'

class ViewPurchaseRequest(BaseRolePermission):
    codename = 'view_purchase_request'
    object_permission = True

class ChangePurchaseRequest(BaseRolePermission):
    codename = 'change_purchase_request'
    object_permission = True

class ApprovePurchaseRequest(BaseRolePermission):
    codename = 'approve_purchase_request'   # renamed for clarity
    object_permission = True

class DeclinePurchaseRequest(BaseRolePermission):
    codename = 'decline_purchase_request'   # renamed for clarity
    object_permission = True

class ManageUsers(BaseRolePermission):
    codename = 'manage_users'


class ViewAnalytics(BaseRolePermission):
    codename = 'view_analytics'

#ViewReimbursementRequest, SubmitReimbursementRequest, ChangeReimbursementRequest
class SubmitReimbursementRequest(BaseRolePermission):
    codename = 'submit_reimbursement_request'

class ViewReimbursementRequest(BaseRolePermission):
    codename = 'view_reimbursement_request'
    object_permission = True

class ApproveReimbursementRequest(BaseRolePermission):
    codename = 'approve_reimbursement_request'   # distinct from purchase
    object_permission = True

class DeclineReimbursementRequest(BaseRolePermission):
    codename = 'decline_reimbursement_request'   # distinct from purchase
    object_permission = True

class DisburseReimbursementRequest(BaseRolePermission):
    codename = 'disburse_reimbursement'   # distinct from purchase
    object_permission = True
