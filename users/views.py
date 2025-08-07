import uuid
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from helpers.exceptions import CustomValidationException
from helpers.response import CustomResponse
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from django.views import View
from drf_spectacular.utils import extend_schema
from users.auth_utils import (
    create_or_update_user,
    generate_pkce_verifier,
    fetch_token_data,
)
from django.shortcuts import redirect
from django.utils.crypto import get_random_string
from urllib.parse import urlencode
from .models import *
from rest_framework.exceptions import AuthenticationFailed, ValidationError, APIException
from django.http import JsonResponse
from .serializers import UserSerializer
from urllib.parse import urlencode
from django.db.models import Q, Count

User = get_user_model()

from utils.permissions import *
from rest_framework.permissions import IsAuthenticated
from .auth import JWTAuthenticationFromCookie
from django.http import HttpResponseRedirect
from rest_framework.pagination import PageNumberPagination
 

@extend_schema(
    summary="User Login with Azure AD",
    description="Initiates login with Azure Active Directory by redirecting to the Microsoft login page.",
)
class AzureLoginView(APIView):
    authentication_classes = []  # Allow unauthenticated access
    permission_classes = []

    def get(self, request):
        # Generate PKCE verifier and challenge
        verifier, challenge = generate_pkce_verifier()

        # Generate state and save to database
        state = str(uuid.uuid4())
        OAuthState.objects.create(
            state=state,
            pkce_verifier=verifier
        )

        # Clean up expired states
        OAuthState.cleanup_expired()

        # Generate Azure AD authorization URL with the updated scope
        authorization_url = (
            f"{settings.AZURE_AD_AUTHORITY}/oauth2/v2.0/authorize?"
            f"client_id={settings.AZURE_AD_CLIENT_ID}&response_type=code&"
            f"redirect_uri={settings.AZURE_AD_REDIRECT_URI}&"
            f"scope=openid+profile+User.Read+email&"
            f"code_challenge={challenge}&code_challenge_method=S256&"
            f"state={state}"
        )

        return Response({'authorization_url': authorization_url})



# @extend_schema(
#     summary="Azure AD Callback",
#     description="Handles the callback from Azure AD, exchanges the authorization code for tokens, and logs the user in."
# )  
class AzureCallbackView(View):

    def get(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        
        if error:
            error_description = request.GET.get('error_description', 'No description provided.')
            return JsonResponse({'error': error, 'description': error_description}, status=400)


        if not code:
            raise CustomValidationException('Authorization code not provided', 401)

        try:
            # Retrieve and validate state
            oauth_state = OAuthState.objects.get(state=state)

            # Validate if the state is the same
            if oauth_state.state != state:
                raise CustomValidationException('Invalid state parameter. Possible CSRF attack detected.', 401)

            # Get PKCE verifier
            pkce_verifier = oauth_state.pkce_verifier

            
            # Clean up the used state immediately
            oauth_state.delete()

            # Fetch token
            token_data = fetch_token_data(code, pkce_verifier)
            token_response = requests.post(token_data['url'], data=token_data['data']).json()

            access_token = token_response.get('access_token')
            

            if not access_token:
                raise CustomValidationException('Authentication failed', 401)

        
            # Update user and branch
            headers = {'Authorization': f'Bearer {access_token}'}
            graph_data = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers).json()
            try:
                user = create_or_update_user(graph_data)
            except Exception as e:
                
                raise CustomValidationException("Error occurred while creating user!", 401)
            

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            print(f"Access Token: {access_token}")
            # Create HTTP-only cookies for access and refresh tokens
            response = HttpResponseRedirect(settings.FRONTEND_URL + '/auth-success')
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=True,
                samesite='None',
                max_age=3600
            )
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=True,
                samesite='None',
                max_age=7 * 24 * 3600
            )
            return response
        
            # Create redirect response
            # response = JsonResponse({'message': 'Login successful'})
            # response['Location'] = settings.FRONTEND_URL + '/auth-success'
            # response.status_code = 302
            # return redirect(redirect_url)

        except OAuthState.DoesNotExist:
            # For OAuth specific errors, we might want to keep the redirect behavior
            frontend_error_url = f"{settings.FRONTEND_URL}/auth-error?error=invalid_state"
            return redirect(frontend_error_url)
        except (ValidationError, AuthenticationFailed, APIException) as e:
            # Let these exceptions be handled by the custom exception handler
            raise
        except Exception as e:
            frontend_error_url = f"{settings.FRONTEND_URL}/auth-error?error=auth_failed"
            return redirect(frontend_error_url)
        
        
@extend_schema(
    summary="Logout User",
    description="Logs out the current user by clearing authentication tokens."
)
class AzureLogoutView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            # Clear cookies (if applicable)
            response = Response(
                {
                    'message': 'Logout successful',
                    'redirect_url': settings.FRONTEND_URL
                },
                status=status.HTTP_200_OK
            )
            response.delete_cookie('access_token')
            response.delete_cookie('refresh_token')

            # Optionally notify Azure (note: Azure AD logout is typically just a redirect)
            azure_logout_url = settings.AZURE_AD_LOGOUT_URL
            requests.get(azure_logout_url)

            return response

        except Exception as e:
            frontend_error_url = f"{settings.FRONTEND_URL}/auth-error?error=logout_failed"
            return Response(
                {
                    "detail": "Logout failed",
                    "redirect_url": frontend_error_url,
                    "more_detail": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
#Get authenticated user details
@extend_schema(
    summary="Get Authenticated User Details"
)
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthenticationFromCookie]
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)         

class UserView(APIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, ManageUsers]
    authentication_classes = [JWTAuthenticationFromCookie]
    """
    API endpoint to list and add users in the system.
    
    Returns a list of all users with their details.
    """
    def get(self, request):
        users = User.objects.all()
        
         # Count active and inactive users
        active_count = users.filter(is_active=True).count()
        inactive_count = users.filter(is_active=False).count()


        paginator = PageNumberPagination()
        paginated_users = paginator.paginate_queryset(users, request)

        serializer = UserSerializer(paginated_users, many=True)

        response_data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "active": active_count,
            "inactive": inactive_count
        }

        return CustomResponse(True, "Users retrieved successfully", data=response_data)

   
    def post(self, request):
        """
        Add a user to the system.
         """
         
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return CustomResponse(True, "User Created successfully", data=serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request):
        """
        Update an existing user.
        """
        user_id = request.data.get('id')
        if not user_id:
            return Response({"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User updated successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class SearchUserView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ManageUsers]
    def get(self, request):
        search_query = request.query_params.get('q', '').strip()
        if not search_query:
            return CustomResponse(False, "Search query is required", 400)

        users = User.objects.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
        
         # Count active and inactive users
        active_count = users.filter(is_active=True).count()
        inactive_count = users.filter(is_active=False).count()


        paginator = PageNumberPagination()
        paginated_users = paginator.paginate_queryset(users, request)

        serializer = UserSerializer(paginated_users, many=True)

        response_data = {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": serializer.data,
            "active": active_count,
            "inactive": inactive_count,
            
        }

        return CustomResponse(True, "Search successful", 200, response_data)

class ToggleUserActivationView(APIView):
    authentication_classes = [JWTAuthenticationFromCookie]
    permission_classes = [IsAuthenticated, ManageUsers]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.is_active = not user.is_active
            user.save()

            # Count active and inactive users
            active_count = User.objects.filter(is_active=True).count()
            inactive_count = User.objects.filter(is_active=False).count()

            status_msg = "User reactivated successfully" if user.is_active else "User deactivated successfully"

            return CustomResponse(
                True,
                status_msg,
                200,
                {
                    "user_id": str(user.id),
                    "is_active": user.is_active,
                    "active_users": active_count,
                    "inactive_users": inactive_count
                }
            )
        except User.DoesNotExist:
            return CustomResponse(False, "User not found", 404)

class DummyLogin(APIView):
    """
    Dummy login view for testing purposes.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        email = request.GET.get('email')
        if not email:
            return CustomResponse(False,  "Email parameter is required")
        
        user = User.objects.filter(email=email).first()
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        print(f"Access Token: {access_token}")
        # Create HTTP-only cookies for access and refresh tokens
        response = CustomResponse(True,  'Login successful')
        response.set_cookie(
            key='access_token',
            value=access_token,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=3600
        )
        response.set_cookie(
            key='refresh_token',
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=7 * 24 * 3600
        )

        # Redirect to frontend
        response['Location'] = settings.FRONTEND_URL + '/auth-success'
        response.status_code = 302
        return response