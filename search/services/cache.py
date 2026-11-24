"""Database-backed result cache (SearchCache)."""
import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ..models import SearchCache


def normalize_text(text):
    """Lowercase with Turkish rules (İ -> i, I -> ı), trim, collapse whitespace."""
    text = (text or "").replace("İ", "i").replace("I", "ı").lower()
    return " ".join(text.split())


def cache_params(req):
    f = req.filters
    return {
        "filters": {
            "min_price": f.min_price,
            "max_price": f.max_price,
            "min_rating": f.min_rating,
            "limit": f.limit,
        },
        "custom_criteria": normalize_text(req.custom_criteria),
    }


def make_cache_key(req, country):
    """sha256 of the normalized request.

    `provider` is part of the key (a small addition to the spec) so that mock
    results can never be served after switching to the real provider.
    """
    payload = {
        "query": normalize_text(req.query),
        "country": country,
        "mode": req.mode,
        "provider": settings.LLM_PROVIDER,
        **cache_params(req),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(key):
    """Return the valid (unexpired) cache row or None. Expired rows are ignored."""
    return SearchCache.objects.filter(cache_key=key, expires_at__gt=timezone.now()).first()


def store(key, req, country, data):
    now = timezone.now()
    SearchCache.objects.update_or_create(
        cache_key=key,
        defaults={
            "query": normalize_text(req.query)[:200],
            "country": country,
            "mode": req.mode,
            "params": cache_params(req),
            "result": data,
            "created_at": now,
            "expires_at": now + timedelta(hours=settings.CACHE_TTL_HOURS),
        },
    )


def purge_expired():
    deleted, _ = SearchCache.objects.filter(expires_at__lte=timezone.now()).delete()
    return deleted
