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

    user, _ = User.objects.update_or_create(
        microsoft_ad_id=microsoft_ad_id,
        defaults={
            'email': email,
            'username': email,
            'name': name,
        }
    )
    return user

def fetch_and_update_user_groups_and_roles(headers, user):
    response = requests.get(
        'https://graph.microsoft.com/v1.0/me/memberOf',
        headers=headers
    )

    groups = []
    if response.status_code == 200:
        data = response.json()
        groups = [entry.get("displayName") for entry in data.get("value", []) if "displayName" in entry]

    # You can plug in your own logic to assign roles/permissions from groups
    permissions = ['read', 'write']  # Simplified example

    return {
        'groups': groups,
        'permissions': permissions,
    }


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