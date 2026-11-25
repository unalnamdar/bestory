import re

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

RESERVED_USERNAMES = frozenset({
    "admin", "administrator", "bestory", "api", "root", "support",
    "destek", "moderator", "null", "undefined",
})

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")


def validate_username(value):
    """Username rules: 3-20 chars of a-z, 0-9, _ and . (case-insensitive input)."""
    value = (value or "").lower()
    if not USERNAME_RE.match(value):
        raise ValidationError(
            "Kullanıcı adı 3-20 karakter olmalı; yalnızca harf, rakam, _ ve . kullanılabilir."
        )
    if value in RESERVED_USERNAMES:
        raise ValidationError("Bu kullanıcı adı kullanılamaz.")


class User(AbstractUser):
    """Custom user. username and email are always stored lowercase.

    The email is private: it must never appear in public templates, API
    responses or logs (only on the user's own profile page).
    """

    username = models.CharField(
        "kullanıcı adı",
        max_length=20,
        unique=True,
        validators=[validate_username],
        error_messages={"unique": "Bu kullanıcı adı zaten alınmış."},
    )
    email = models.EmailField(
        "e-posta",
        unique=True,
        error_messages={"unique": "Bu e-posta adresi zaten kayıtlı."},
    )
    # first_name / last_name are not used.
    first_name = None
    last_name = None

    def clean(self):
        super().clean()
        self.username = (self.username or "").lower()
        self.email = (self.email or "").lower()

    def save(self, *args, **kwargs):
        self.username = (self.username or "").lower()
        self.email = (self.email or "").lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.username

    def get_short_name(self):
        return self.username


class LoginAttempt(models.Model):
    """One row per FAILED sign-in, used to throttle guessing (see accounts/throttle.py).

    Only salted hashes are stored: never the raw IP and never the typed identifier.
    """

    ip_hash = models.CharField(max_length=64, db_index=True)
    identifier_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
