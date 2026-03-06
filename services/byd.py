
import base64
import requests
from rest_framework.exceptions import ValidationError

class BYD:
    def __init__(self, url:str=None):
        self.base_url = url or "https://fcegrn.xyz/API/imprest/v1/"

    def get_headers(self):
        """Get authorization header. """
        try:
            password = "@deb0L4"
            username = "adebola"
            auth_string = f"{username}:{password}"
            auth_header = f"Basic {base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')}"
            # headers = {
            #     'Authorization': auth_header,
            #     'Content-Type': 'application/x-www-form-urlencoded'
            # }
            headers = {
                'Authorization': auth_header,
                'Content-Type': 'application/json'
            }
            return headers
        except Exception as err:
            raise err

    def _fetch_items(self, path:str=None, params:dict={}):
        """Fetch items from the specified url"""
        try:
            if path:
                url = self.base_url + path
                response = requests.get(url=url, headers=self.get_headers(), params=params)
                if response.status_code == 200:
                    data_:dict = response.json()
                    return data_.get("data", [])
            else:
                raise ValidationError("URL Path must be provided.")
        except Exception as err:
            raise err

    def get_expense_items(self, **params):
        """Get the list of expense items from BYD. """
        try:
            path="expense-accounts/"
            return self._fetch_items(path=path, params={**params})
        except Exception as err:
            return None

    def get_banks(self, **params):
        """Get list of banks from BYD. """
        try:
            path="bank-accounts/"
            return self._fetch_items(path=path, params={**params})
        except Exception as err:
            return None

api = BYD()