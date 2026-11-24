"""Supported countries, currencies and store hints (hints, not mandatory sources)."""
from django.conf import settings

COUNTRIES = {
    "TR": {"name": "Türkiye", "currency": "TRY", "stores": ["Trendyol", "Hepsiburada", "Amazon.com.tr", "n11"]},
    "US": {"name": "ABD", "currency": "USD", "stores": ["Amazon.com", "Best Buy", "Walmart"]},
    "DE": {"name": "Almanya", "currency": "EUR", "stores": ["Amazon.de", "Otto", "MediaMarkt"]},
    "GB": {"name": "Birleşik Krallık", "currency": "GBP", "stores": ["Amazon.co.uk", "Argos", "Currys"]},
    "FR": {"name": "Fransa", "currency": "EUR", "stores": ["Amazon.fr", "Fnac", "Cdiscount"]},
    "NL": {"name": "Hollanda", "currency": "EUR", "stores": ["Bol.com", "Coolblue", "Amazon.nl"]},
    "AZ": {"name": "Azerbaycan", "currency": "AZN", "stores": ["Umico", "Kontakt Home", "Irshad"]},
}


def is_supported(code):
    return isinstance(code, str) and code.upper() in COUNTRIES


def default_country():
    code = (getattr(settings, "DEFAULT_COUNTRY", "TR") or "TR").upper()
    return code if code in COUNTRIES else "TR"


def detect_country(request, requested=None):
    """Order: explicit request > x-vercel-ip-country header (if supported) > default."""
    if requested and is_supported(requested):
        return requested.upper()
    header = request.headers.get("x-vercel-ip-country", "")
    if is_supported(header):
        return header.upper()
    return default_country()


def country_choices():
    return [(code, info["name"]) for code, info in COUNTRIES.items()]
