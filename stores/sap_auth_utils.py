from imprest_portal import settings
from typing import Any, Dict
import requests



#function to simulate token generation from sap
def fetch_sap_token():
    url = f"{settings.SAP_URL}/api/v1/authenticate"
    payload = {
        "username": settings.SAP_TOKEN_USERNAME,
        "password": settings.SAP_TOKEN_PASSWORD
    }
    print(settings.SAP_TOKEN_USERNAME, settings.SAP_TOKEN_PASSWORD)
    response = requests.post(url, json=payload) 
    print("SAP Token Response Status Code:", response.status_code)
    response.raise_for_status()
    token_data = response.json()    
    access_token = token_data.get("data", {}).get("access")
    print("SAP Access Token:", access_token)
    return access_token
