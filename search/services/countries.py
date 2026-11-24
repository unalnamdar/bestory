"""Supported countries, currencies and store hints (hints, not mandatory sources)."""
from django.conf import settings

COUNTRIES = {
    "TR": {"name": "Türkiye", "currency": "TRY", "stores": ["Trendyol", "Hepsiburada", "Amazon.com.tr", "n11"], "timezone": "Europe/Istanbul", "tavily_country": "turkey"},
    "US": {"name": "ABD", "currency": "USD", "stores": ["Amazon.com", "Best Buy", "Walmart"], "timezone": "America/New_York", "tavily_country": "united states"},
    "DE": {"name": "Almanya", "currency": "EUR", "stores": ["Amazon.de", "Otto", "MediaMarkt"], "timezone": "Europe/Berlin", "tavily_country": "germany"},
    "GB": {"name": "Birleşik Krallık", "currency": "GBP", "stores": ["Amazon.co.uk", "Argos", "Currys"], "timezone": "Europe/London", "tavily_country": "united kingdom"},
    "FR": {"name": "Fransa", "currency": "EUR", "stores": ["Amazon.fr", "Fnac", "Cdiscount"], "timezone": "Europe/Paris", "tavily_country": "france"},
    "NL": {"name": "Hollanda", "currency": "EUR", "stores": ["Bol.com", "Coolblue", "Amazon.nl"], "timezone": "Europe/Amsterdam", "tavily_country": "netherlands"},
    "AZ": {"name": "Azerbaycan", "currency": "AZN", "stores": ["Umico", "Kontakt Home", "Irshad"], "timezone": "Asia/Baku", "tavily_country": "azerbaijan"},
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
