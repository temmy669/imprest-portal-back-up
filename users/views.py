import uuid
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status
from drf_spectacular.utils import extend_schema

User = get_user_model()


@extend_schema(
    summary="User Login with Azure AD",
    description="Initiates login with Azure Active Directory by redirecting to the Microsoft login page."
)
class AzureLoginView(APIView):
    authentication_classes = []  # Allow unauthenticated access
    permission_classes = []

    def get(self, request):
        state = str(uuid.uuid4())
        request.session['oauth_state'] = state

        authorization_url = (
            f"{settings.AZURE_AD_AUTHORITY}/oauth2/v2.0/authorize?"
            f"client_id={settings.AZURE_AD_CLIENT_ID}&response_type=code&"
            f"redirect_uri={settings.AZURE_AD_REDIRECT_URI}&"
            f"scope=openid profile email User.Read&"
            f"response_mode=query&state={state}"
        )
        return Response({"auth_url": authorization_url}, status=status.HTTP_200_OK)


@extend_schema(
    summary="Azure AD Callback",
    description="Handles the callback from Azure AD, exchanges the authorization code for tokens, and logs the user in."
)
class AzureCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state')

        if state != request.session.get('oauth_state'):
            return Response({'error': 'Invalid state'}, status=status.HTTP_400_BAD_REQUEST)

        token_url = f"{settings.AZURE_AD_AUTHORITY}/oauth2/v2.0/token"
        token_data = {
            'client_id': settings.AZURE_AD_CLIENT_ID,
            'scope': 'openid profile email User.Read',
            'code': code,
            'redirect_uri': settings.AZURE_AD_REDIRECT_URI,
            'grant_type': 'authorization_code',
            'client_secret': settings.AZURE_AD_CLIENT_SECRET,
        }

        token_response = requests.post(token_url, data=token_data).json()
        access_token = token_response.get('access_token')

        if not access_token:
            return Response({'error': 'Token fetch failed'}, status=status.HTTP_400_BAD_REQUEST)

        user_info = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers={'Authorization': f'Bearer {access_token}'}
        ).json()

        email = user_info.get('mail') or user_info.get('userPrincipalName')
        name = user_info.get('displayName')

        if not email:
            return Response({'error': 'Email not found'}, status=status.HTTP_400_BAD_REQUEST)

        user, _ = User.objects.get_or_create(email=email, defaults={'full_name': name})

        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Login successful',
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
        }, status=status.HTTP_200_OK)


@extend_schema(
    summary="Logout User",
    description="Logs out the current user by clearing authentication tokens."
)
class AzureLogoutView(APIView):
    def get(self, request):
        response = Response({'message': 'Logged out'}, status=status.HTTP_200_OK)
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response
