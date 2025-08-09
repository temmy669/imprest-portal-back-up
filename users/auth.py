from helpers.exceptions import CustomValidationException
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.request import Request
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.exceptions import AuthenticationFailed

class JWTAuthenticationFromCookie(JWTAuthentication):
    def authenticate(self, request: Request):
        raw_token = request.COOKIES.get('access_token')
       
        if not raw_token:
            # Try header authentication
            print("Authenticating with Bearer token")
            header_auth = super().authenticate(request)
            if header_auth is not None:
                return header_auth
            raise AuthenticationFailed('Authentication token is missing.')
           
        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            if not  user.is_active:
                raise CustomValidationException("Your account is not active. Please contact your administrator.")
            return self.get_user(validated_token), validated_token
        except TokenError as e:
            raise AuthenticationFailed(f'Invalid token: {str(e)}')