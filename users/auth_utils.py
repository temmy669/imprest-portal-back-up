import requests
import base64
import hashlib
import os
from django.contrib.auth import get_user_model
from imprest_portal import settings
from typing import Any, Dict

User = get_user_model()

def generate_pkce_verifier():
    """Generate a secure random PKCE verifier."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return verifier, challenge



def create_or_update_user(graph_data):
    microsoft_ad_id = graph_data.get('id')
    email = graph_data.get('mail') or graph_data.get('userPrincipalName')
    name = graph_data.get('displayName')

    # First, try to find user by microsoft_ad_id
    user = User.objects.filter(microsoft_ad_id=microsoft_ad_id).first()

    if user:
        # Update existing user
        user.email = email
        user.username = email
        user.name = name
        user.save()
        return user

    # If not found, check by email (in case user was created manually)
    user = User.objects.filter(email=email).first()
    if user:
        # Link AD ID to existing user
        user.microsoft_ad_id = microsoft_ad_id
        user.name = name
        user.username = email
        user.save()
        return user

    # Otherwise, create a new user
    user = User.objects.create(
        microsoft_ad_id=microsoft_ad_id,
        email=email,
        username=email,
        name=name
    )
    return user


def fetch_token_data(code: str, verifier: str) -> Dict[str, Any]:
        return {
            'url': f"{settings.AZURE_AD_AUTHORITY}/oauth2/v2.0/token",
            'data': {
                'client_id': settings.AZURE_AD_CLIENT_ID,
                'client_secret': settings.AZURE_AD_CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': settings.AZURE_AD_REDIRECT_URI,
                'code_verifier': verifier,
                'scope': 'openid profile User.Read email',
            },
        }