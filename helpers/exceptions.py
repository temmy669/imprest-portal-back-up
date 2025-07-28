from rest_framework.exceptions import APIException


class CustomValidationException(APIException):
    default_detail = "You do not have the required permissions to complete the action you have requested for."

    def __init__(self, detail=None, code=None):
        if detail is not None:
            self.detail = detail
        else:
            self.detail = self.default_detail

        if code is None:
            self.status_code = 400
        else:
            self.status_code = code
