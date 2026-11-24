"""Supported countries, currencies and store hints (hints, not mandatory sources)."""
from django.conf import settings

# stores = display names used in prompts; store_domains / comparison_sites = domains that the
# Tavily search prefers (not exclusive). compare_search = code-built product search link used as
# an extra source when the model only found category/article pages (Turkey only: verified).
COUNTRIES = {
    "TR": {
        "name": "Türkiye", "currency": "TRY", "timezone": "Europe/Istanbul", "tavily_country": "turkey",
        "stores": ["Trendyol", "Hepsiburada", "Amazon.com.tr", "n11"],
        "store_domains": ["trendyol.com", "hepsiburada.com", "n11.com", "amazon.com.tr"],
        "comparison_sites": ["akakce.com", "cimri.com", "epey.com"],
        "compare_search": ("Akakçe'de bu ürünü ara", "https://www.akakce.com/arama/?q={q}"),
    },
    "US": {
        "name": "ABD", "currency": "USD", "timezone": "America/New_York", "tavily_country": "united states",
        "stores": ["Amazon.com", "Best Buy", "Walmart"],
        "store_domains": ["amazon.com", "bestbuy.com", "walmart.com"],
        "comparison_sites": [],
    },
    "DE": {
        "name": "Almanya", "currency": "EUR", "timezone": "Europe/Berlin", "tavily_country": "germany",
        "stores": ["Amazon.de", "Otto", "MediaMarkt"],
        "store_domains": ["amazon.de", "otto.de", "mediamarkt.de"],
        "comparison_sites": ["idealo.de", "geizhals.de"],
    },
    "GB": {
        "name": "Birleşik Krallık", "currency": "GBP", "timezone": "Europe/London", "tavily_country": "united kingdom",
        "stores": ["Amazon.co.uk", "Argos", "Currys"],
        "store_domains": ["amazon.co.uk", "argos.co.uk", "currys.co.uk"],
        "comparison_sites": ["pricerunner.com", "idealo.co.uk"],
    },
    "FR": {
        "name": "Fransa", "currency": "EUR", "timezone": "Europe/Paris", "tavily_country": "france",
        "stores": ["Amazon.fr", "Fnac", "Cdiscount"],
        "store_domains": ["amazon.fr", "fnac.com", "cdiscount.com"],
        "comparison_sites": ["idealo.fr"],
    },
    "NL": {
        "name": "Hollanda", "currency": "EUR", "timezone": "Europe/Amsterdam", "tavily_country": "netherlands",
        "stores": ["Bol.com", "Coolblue", "Amazon.nl"],
        "store_domains": ["bol.com", "coolblue.nl", "amazon.nl"],
        "comparison_sites": ["tweakers.net", "kieskeurig.nl"],
    },
    "AZ": {
        "name": "Azerbaycan", "currency": "AZN", "timezone": "Asia/Baku", "tavily_country": "azerbaijan",
        "stores": ["Umico", "Kontakt Home", "Irshad"],
        "store_domains": ["umico.az", "kontakt.az", "irshad.az"],
        "comparison_sites": [],
    },
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
