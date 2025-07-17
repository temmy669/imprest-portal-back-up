import uuid
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.views import View
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

class AzureLoginView(View):
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

        return HttpResponseRedirect(authorization_url)

class AzureCallbackView(View):
    def get(self, request):
        code = request.GET.get('code')
        state = request.GET.get('state')

        if state != request.session.get('oauth_state'):
            return JsonResponse({'error': 'Invalid state'}, status=400)

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
            return JsonResponse({'error': 'Token fetch failed'}, status=400)

        user_info = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers={'Authorization': f'Bearer {access_token}'}
        ).json()

        email = user_info.get('mail') or user_info.get('userPrincipalName')
        name = user_info.get('displayName')

        if not email:
            return JsonResponse({'error': 'Email not found'}, status=400)

        user, _ = User.objects.get_or_create(email=email, defaults={'full_name': name})

        refresh = RefreshToken.for_user(user)
        response = JsonResponse({'message': 'Login successful'})
        response.set_cookie('access_token', str(refresh.access_token), httponly=True)
        response.set_cookie('refresh_token', str(refresh), httponly=True)

        return response

class AzureLogoutView(View):
    def get(self, request):
        response = JsonResponse({'message': 'Logged out'})
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response
