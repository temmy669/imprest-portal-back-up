from django.core.exceptions import PermissionDenied

def check_permission(user, codename=None, amount=None):
    """
    Universal permission checker with:
    - Admin override (if user.is_superuser or role.is_admin_role)
    - Codename-based permission checks
    - Amount-based approval thresholds (for purchases)
    """
    # Admin/Superuser bypass
    if getattr(user, 'is_superuser', False) or user.role.name =='Admin':
        return True
    
    # Standard permission check
    if codename:
        return user.role.permissions.filter(codename=codename).exists()
    
    # Amount-based approval logic (for purchase requests)
    if amount is not None:
        if amount >= 5000:
            return user.role.permissions.filter(codename='approve_over_5000').exists()
    return False

def permission_required(codename=None, amount_threshold=None):
    """
    Enhanced decorator supporting:
    - @permission_required('add_user')  # Codename check
    - @permission_required(amount_threshold=5000)  # Amount check
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            has_perm = check_permission(
                request.user, 
                codename=codename,
                amount=amount_threshold
            )
            if not has_perm:
                raise PermissionDenied("Missing required permission")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator