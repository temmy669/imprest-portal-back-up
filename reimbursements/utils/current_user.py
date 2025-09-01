import threading

_user_storage = threading.local()

def set_current_user(user):
    _user_storage.user = user

def get_current_user():
    return getattr(_user_storage, 'user', None)

def clear_current_user():
    if hasattr(_user_storage, 'user'):
        del _user_storage.user
