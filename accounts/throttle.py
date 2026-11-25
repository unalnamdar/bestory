"""Simple brute-force protection for sign-in, backed by the database.

Serverless instances do not share memory, so a per-process cache would not work; failed
attempts are stored in `LoginAttempt` (salted hashes only, no new package needed).

- per IP: 10 failures in 10 minutes
- per account identifier: 5 failures in 10 minutes (across all IPs). This can temporarily lock a
  victim's account for 10 minutes; that is the accepted trade-off for a prototype.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from search.services.ratelimit import format_wait

from .models import LoginAttempt

WINDOW = timedelta(minutes=10)
IP_LIMIT = 10
IDENTIFIER_LIMIT = 5
KEEP = timedelta(days=1)


def hash_identifier(identifier):
    value = f"id:{(identifier or '').strip().lower()}{settings.IP_HASH_SALT}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def blocked_message(ip_hash, identifier):
    """Return a Turkish "wait N minutes" message if this sign-in must be refused, else None."""
    since = timezone.now() - WINDOW
    recent = LoginAttempt.objects.filter(created_at__gte=since)
    id_hash = hash_identifier(identifier)
    checks = (
        (recent.filter(ip_hash=ip_hash), IP_LIMIT),
        (recent.filter(identifier_hash=id_hash), IDENTIFIER_LIMIT),
    )
    wait = 0
    for qs, limit in checks:
        count = qs.count()
        if count >= limit:
            # The block ends when the oldest counted failure leaves the window.
            oldest = qs.order_by("created_at")[count - limit]
            wait = max(wait, int((oldest.created_at + WINDOW - timezone.now()).total_seconds()))
    if wait > 0:
        return f"Çok fazla başarısız deneme. Yaklaşık {format_wait(wait)} sonra tekrar dene."
    return None


def record_failure(ip_hash, identifier):
    LoginAttempt.objects.create(ip_hash=ip_hash, identifier_hash=hash_identifier(identifier))
    LoginAttempt.objects.filter(created_at__lt=timezone.now() - KEEP).delete()  # keep the table small
