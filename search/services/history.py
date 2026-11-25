"""A member's recent searches, as links that reopen the same search.

The link carries exactly the parameters search.js sends, so reopening a search
within CACHE_TTL_HOURS produces the same cache key and is served from the cache.
"""
import json
from urllib.parse import urlencode

from ..models import SearchCache, SearchLog
from .cache import normalize_text
from .countries import COUNTRIES

MODE_LABELS = dict(SearchCache.MODE_CHOICES)
SCAN_ROWS = 100  # enough rows to find 10 distinct searches without loading the whole log


def _num(value):
    """2000.0 -> "2000", 4.5 -> "4.5" (matches how JavaScript prints numbers)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def search_url(query, country, mode, params):
    params = params or {}
    filters = params.get("filters") or {}
    q = [("q", query), ("country", country), ("mode", mode)]
    for name in ("min_price", "max_price", "min_rating"):
        if filters.get(name) is not None:
            q.append((name, _num(filters[name])))
    if filters.get("limit") not in (None, 10):
        q.append(("limit", _num(filters["limit"])))
    if params.get("custom_criteria"):
        q.append(("custom", params["custom_criteria"]))
    return "/?" + urlencode(q)


def recent_searches(user, limit=10):
    """The user's last `limit` distinct successful searches, newest first."""
    rows = (
        SearchLog.objects.filter(user=user, status="ok")
        .order_by("-created_at", "-id")  # id breaks ties between rows saved in the same instant
        .values("query", "country", "mode", "params", "created_at")[:SCAN_ROWS]
    )
    seen, items = set(), []
    for row in rows:
        params = row["params"] or {}
        key = (
            normalize_text(row["query"]),
            row["country"],
            row["mode"],
            json.dumps(params.get("filters") or {}, sort_keys=True),
            normalize_text(params.get("custom_criteria") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        country = COUNTRIES.get(row["country"], {})
        items.append({
            "query": row["query"],
            "country_name": country.get("name", row["country"]),
            "mode_label": MODE_LABELS.get(row["mode"], row["mode"]),
            "custom_criteria": params.get("custom_criteria") or "",
            "created_at": row["created_at"],
            "url": search_url(row["query"], row["country"], row["mode"], params),
        })
        if len(items) >= limit:
            break
    return items
