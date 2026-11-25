"""Price rules applied in code, whatever the model says.

1. Filters: the user's min/max budget is enforced here, not trusted to the model.
2. Evidence (only when the provider supplies the raw search snippets, i.e. Tavily + Gemini):
   every product must carry a `price_evidence` {url, quote}. The quote must appear word for
   word in that result's snippet, and must contain the price next to a currency marker.
   Products whose price cannot be proven this way are dropped.
3. The schema separately requires price_min > 0, price_max >= price_min and a plausible spread.
"""
import re
from urllib.parse import urlparse

TOLERANCE = 0.5  # currency units; prices are compared after parsing, so formatting is irrelevant

_NUMBER_RE = re.compile(r"\d(?:[\d.,   ]*\d)?")
_MARKER = (
    r"(?:tl|try|usd|eur|gbp|azn|lira|manat|dollars?|euros?|pounds?)(?![a-zçğıöşüâîû])"
    r"|[₺$€£₼]"
)
# The marker must touch the number (at most 2 spaces between): "579 TL", "₺1.299", "TL 579".
# A looser window wrongly turned model names like "Buds 6 Play 579 TL" into a price of 6.
_AFTER_RE = re.compile(r"^\s{0,2}(?:" + _MARKER + r")", re.I)
_BEFORE_RE = re.compile(r"(?<![a-zçğıöşüâîû])(?:" + _MARKER + r")\s{0,2}$", re.I)


def parse_number(token):
    """Parse '1.299,00', '1,299.00', '1299', '1 299', '579,90' into a float (or None)."""
    token = re.sub(r"[   ]", "", token.strip())
    if not token or not re.fullmatch(r"[\d.,]+", token):
        return None
    has_dot, has_comma = "." in token, "," in token
    if has_dot and has_comma:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        token = token.replace(thousands, "").replace(decimal, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        parts = token.split(sep)
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            token = "".join(parts)            # 1.299 / 1,299 / 1.299.000 -> thousands separators
        else:
            token = parts[0] + "." + parts[1]  # 579,90 / 579.90 -> decimal separator
    try:
        return float(token)
    except ValueError:
        return None


def prices_in_text(text):
    """Numbers directly next to a currency marker (TL, ₺, USD, $, EUR...)."""
    text = text or ""
    found = []
    for match in _NUMBER_RE.finditer(text):
        if not (_AFTER_RE.match(text[match.end(): match.end() + 12])
                or _BEFORE_RE.search(text[max(0, match.start() - 12): match.start()])):
            continue
        value = parse_number(match.group())
        if value is not None:
            found.append(value)
    return found


def _norm_ws(text):
    return " ".join((text or "").split()).lower()


def _norm_url(url):
    return (url or "").strip().split("#")[0].rstrip("/").lower()


def _has_value(values, target):
    return any(abs(v - target) <= TOLERANCE for v in values)


def host_of(url):
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def enforce_filters(data, req):
    """Drop products without a price or outside the requested budget. Returns the drop count."""
    f = req.filters
    kept, dropped = [], 0
    for item in data.get("products") or []:
        low, high = _as_float(item, "price_min"), _as_float(item, "price_max")
        if low is None or low <= 0:
            dropped += 1
            continue
        high = high if high is not None else low
        if f.max_price is not None and low > f.max_price:
            dropped += 1
            continue
        if f.min_price is not None and high < f.min_price:
            dropped += 1
            continue
        kept.append(item)
    data["products"] = kept
    return dropped


def _as_float(item, key):
    try:
        value = item.get(key) if isinstance(item, dict) else None
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def verify_evidence(data, source_texts):
    """Keep only products whose price is proven by a verbatim quote from a real snippet.

    `source_texts` maps result URL -> snippet text (title + content). On success the product
    gets `price_source` (host of the evidence page) and the evidence field is removed.
    Returns the number of dropped products.
    """
    texts = {_norm_url(u): t for u, t in source_texts.items()}
    kept, dropped = [], 0
    for item in data.get("products") or []:
        if not isinstance(item, dict) or not _evidence_ok(item, texts):
            dropped += 1
            continue
        kept.append(item)
    data["products"] = kept
    return dropped


def _evidence_ok(item, texts):
    low, high = _as_float(item, "price_min"), _as_float(item, "price_max")
    evidence = item.get("price_evidence")
    if low is None or not isinstance(evidence, dict):
        return False
    url, quote = _norm_url(evidence.get("url")), _norm_ws(evidence.get("quote"))
    snippet = texts.get(url)
    if not snippet or len(quote) < 3 or quote not in _norm_ws(snippet):
        return False  # the quote is not in the snippet: the model made it up or altered it
    if not _has_value(prices_in_text(evidence.get("quote", "")), low):
        return False  # the quote does not contain the stated price next to a currency marker
    if high is not None and abs(high - low) > TOLERANCE:
        cited = [url] + [_norm_url(s.get("url")) for s in item.get("sources") or [] if isinstance(s, dict)]
        pool = [v for u in cited if u in texts for v in prices_in_text(texts[u])]
        if not _has_value(pool, high):
            return False  # the upper price appears nowhere in the cited pages
    item["price_source"] = host_of(evidence.get("url"))
    # The evidence page is a source too, so the user can see where the price came from.
    sources = item.setdefault("sources", [])
    if isinstance(sources, list) and not any(
        isinstance(s, dict) and _norm_url(s.get("url")) == url for s in sources
    ):
        sources.append({"title": f"Fiyat kaynağı ({host_of(evidence.get('url'))})", "url": evidence.get("url")})
    item.pop("price_evidence", None)
    return True
