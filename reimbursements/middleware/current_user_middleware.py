from ..utils.current_user import set_current_user, clear_current_user

class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Before view
        if request.user.is_authenticated:
            set_current_user(request.user)
        else:
            clear_current_user()

        response = self.get_response(request)

        # After response
        clear_current_user()
        return response
