"""Bestory-specific `manage.py check --deploy` warnings."""
from django.conf import settings
from django.core.checks import Tags, Warning, register

WEAK_SALTS = {"", "change-me"}


@register(Tags.security, deploy=True)
def ip_hash_salt_check(app_configs, **kwargs):
    if settings.IP_HASH_SALT in WEAK_SALTS or len(settings.IP_HASH_SALT) < 16:
        return [Warning(
            "IP_HASH_SALT is missing, the example value or shorter than 16 characters.",
            hint="Set a long random IP_HASH_SALT in the production environment (see README).",
            id="bestory.W001",
        )]
    return []
