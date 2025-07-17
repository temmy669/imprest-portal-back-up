from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.request import Request
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.exceptions import AuthenticationFailed

class JWTAuthenticationFromCookie(JWTAuthentication):
    def authenticate(self, request: Request):
        raw_token = request.COOKIES.get('access_token')
        if not raw_token:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except TokenError as e:
            raise AuthenticationFailed(f'Invalid token: {str(e)}')