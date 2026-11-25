from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with either the e-mail address or the username (case-insensitive).

    Both are stored lowercase, and a username can never contain "@", so an "@" in the typed
    identifier reliably means e-mail. Permission checks are inherited from ModelBackend.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if not username or not password:
            return None
        identifier = username.strip().lower()
        field = "email" if "@" in identifier else "username"
        try:
            user = User.objects.get(**{field: identifier})
        except User.DoesNotExist:
            # Hash anyway so a missing account takes as long as a wrong password.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
