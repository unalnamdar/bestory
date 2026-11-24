"""Daily usage limit, counted from SearchLog (no Redis).

Only requests that cost money count: cache hits and requests rejected before the
LLM call (rate_limited) are free.
"""
import hashlib
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ..models import SearchLog

WINDOW = timedelta(hours=24)
COUNTED_STATUSES = ("ok", "provider_error", "timeout", "not_a_product")


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hash_ip(ip):
    """sha256(IP + salt). Raw IPs are never stored (KVKK)."""
    return hashlib.sha256(f"{ip}{settings.IP_HASH_SALT}".encode("utf-8")).hexdigest()


def _counted_logs(user, ip_hash):
    qs = SearchLog.objects.filter(
        created_at__gte=timezone.now() - WINDOW,
        cache_hit=False,
        status__in=COUNTED_STATUSES,
    )
    if user is not None:
        return qs.filter(user=user)
    return qs.filter(user__isnull=True, ip_hash=ip_hash)


@dataclass
class Usage:
    limit: int
    used: int
    retry_after_seconds: int = 0

    @property
    def remaining(self):
        return max(0, self.limit - self.used)

    @property
    def blocked(self):
        return self.used >= self.limit


def limit_for(user):
    return settings.RATE_LIMIT_USER_PER_DAY if user is not None else settings.RATE_LIMIT_ANON_PER_DAY


def get_usage(user, ip_hash):
    limit = limit_for(user)
    logs = _counted_logs(user, ip_hash)
    used = logs.count()
    retry_after = 0
    if used >= limit:
        # The window is rolling: a slot frees up when the (used - limit + 1)-th
        # oldest counted request becomes older than 24 hours.
        blocking = logs.order_by("created_at")[used - limit]
        retry_after = max(1, int((blocking.created_at + WINDOW - timezone.now()).total_seconds()))
    return Usage(limit=limit, used=used, retry_after_seconds=retry_after)


def format_wait(seconds):
    minutes = max(1, -(-seconds // 60))  # ceil
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} saat {minutes} dakika"
    if hours:
        return f"{hours} saat"
    return f"{minutes} dakika"
