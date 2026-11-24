"""Main flow (CLAUDE.md section 6.1):

validate (view) -> cache lookup -> rate limit -> prompts -> provider -> extract JSON
-> validate (one repair retry) -> cache write -> SearchLog -> response.
"""
import json
import logging
import time
from datetime import datetime, timezone

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from pydantic import ValidationError

from ..models import SearchLog
from ..providers import get_provider
from ..providers.base import ProviderError, ProviderTimeout
from ..providers.mock import shape_for_request
from . import cache, ratelimit
from .countries import COUNTRIES
from .jsonutil import extract_json  # noqa: F401  (re-exported)
from .prompts import REPAIR_SYSTEM_PROMPT, SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from .schema import Product, SearchResult

logger = logging.getLogger(__name__)

MSG_BAD_RESULT = "Sonuçlar şu an derlenemedi. Lütfen tekrar dene."
MSG_NOT_A_PRODUCT = (
    "Bu bir ürün ya da ürün kategorisi gibi görünmüyor. Satın almak istediğin şeyi yazmayı dene."
)


class AnalysisError(Exception):
    def __init__(self, code, message, status, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}


def _usable(data):
    """True if the parsed JSON is either a not_a_product signal or has a products list."""
    return isinstance(data, dict) and (
        data.get("error") == "not_a_product" or isinstance(data.get("products"), list)
    )


def _norm_url(url):
    url = (url or "").strip().split("#")[0]
    return url.rstrip("/").lower()


def restrict_sources(data, allowed):
    """Keep only sources whose URL is in the allow-list (anti-hallucination).

    Used by providers that hand the model a fixed set of search results: the model
    may only cite pages it was actually given.
    """
    allowed_norm = {_norm_url(u) for u in allowed}
    for item in data.get("products") or []:
        if isinstance(item, dict) and isinstance(item.get("sources"), list):
            item["sources"] = [
                s for s in item["sources"]
                if isinstance(s, dict) and _norm_url(s.get("url")) in allowed_norm
            ]
    return data


def build_result(data, req, country):
    """Validate products one by one, drop invalid ones, enforce limit, re-rank."""
    info = COUNTRIES[country]
    valid = []
    for item in data.get("products") or []:
        try:
            valid.append(Product.model_validate(item))
        except ValidationError:
            continue  # invalid products are discarded
    valid = valid[: req.filters.limit]
    if not valid:
        raise AnalysisError("provider_error", MSG_BAD_RESULT, 502)
    for rank, product in enumerate(valid, start=1):
        product.rank = rank

    result = SearchResult(
        query=req.query,
        country=country,
        currency=info["currency"],
        mode=req.mode,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        summary=str(data.get("summary") or ""),
        products=valid,
        **({"data_note": data["data_note"]} if data.get("data_note") else {}),
    )
    return result.model_dump(mode="json")


def analyze(req, country):
    """Call the provider and return validated result data (no cache, no limits)."""
    try:
        provider = get_provider()
        user_prompt = build_user_prompt(req, country, COUNTRIES[country])
        raw = provider.analyze(SYSTEM_PROMPT, user_prompt, country=country)
        data = extract_json(raw)
        if not _usable(data):
            # One cheap retry without web search: ask the model to fix its JSON.
            logger.warning("Unusable provider output, trying one JSON repair")
            fixed = provider.analyze(
                REPAIR_SYSTEM_PROMPT, build_repair_prompt(raw), country=country, use_search=False
            )
            data = extract_json(fixed)
    except ProviderTimeout as exc:
        raise AnalysisError("timeout", str(exc), 504)
    except ProviderError as exc:
        raise AnalysisError("provider_error", str(exc), 502)

    if not _usable(data):
        raise AnalysisError("provider_error", MSG_BAD_RESULT, 502)
    if data.get("error") == "not_a_product":
        raise AnalysisError("not_a_product", MSG_NOT_A_PRODUCT, 422)
    allowed = getattr(provider, "allowed_source_urls", None)
    if allowed is not None:
        data = restrict_sources(data, allowed)
    if settings.LLM_PROVIDER == "mock":
        data = shape_for_request(data, req)
    return build_result(data, req, country)


def _signup_url():
    try:
        return reverse("accounts:register")
    except NoReverseMatch:  # accounts pages arrive in Phase 3
        return None


def run_search(request, req, country):
    """Full flow. Returns (data, cached, remaining). Raises AnalysisError."""
    started = time.monotonic()
    user = request.user if request.user.is_authenticated else None
    ip_hash = ratelimit.hash_ip(ratelimit.client_ip(request))
    key = cache.make_cache_key(req, country)

    def log(status, cache_hit=False):
        SearchLog.objects.create(
            user=user,
            ip_hash=ip_hash,
            query=req.query[:200],
            country=country,
            mode=req.mode,
            cache_hit=cache_hit,
            status=status,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # 1. Cache hit: instant, free, not counted against the limit.
    hit = cache.get_cached(key)
    if hit is not None:
        usage = ratelimit.get_usage(user, ip_hash)
        log("ok", cache_hit=True)
        return hit.result, True, usage.remaining

    # 2. Rate limit.
    usage = ratelimit.get_usage(user, ip_hash)
    if usage.blocked:
        log("rate_limited")
        wait = ratelimit.format_wait(usage.retry_after_seconds)
        message = f"Günlük arama hakkın doldu. Yaklaşık {wait} sonra tekrar deneyebilirsin."
        extra = {"retry_after": usage.retry_after_seconds}
        if user is None:
            message += " Daha fazla arama için ücretsiz üye ol."
            signup = _signup_url()
            if signup:
                extra["signup_url"] = signup
        raise AnalysisError("rate_limited", message, 429, extra)

    # 3. Analyze, store, log.
    try:
        data = analyze(req, country)
    except AnalysisError as exc:
        status = exc.code if exc.code in ("provider_error", "timeout", "not_a_product") else "provider_error"
        log(status)
        raise
    cache.store(key, req, country, data)
    log("ok")
    return data, False, max(0, usage.remaining - 1)
