"""Main flow: build prompts -> provider -> extract JSON -> validate -> result dict.

Phase 1: no cache, rate limit or log yet (Phase 2).
"""
import json
from datetime import datetime, timezone

from django.conf import settings
from pydantic import ValidationError

from ..providers import get_provider
from ..providers.mock import shape_for_request
from .countries import COUNTRIES
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schema import Product, SearchResult


class AnalysisError(Exception):
    def __init__(self, code, message, status):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def extract_json(raw):
    """Return the first valid JSON object found in the text, or None."""
    text = (raw or "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        start = text.find("{", start + 1)
    return None


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
        raise AnalysisError("provider_error", "Sonuçlar şu an derlenemedi. Lütfen tekrar dene.", 502)
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
    provider = get_provider()
    system_prompt = SYSTEM_PROMPT
    user_prompt = build_user_prompt(req, country, COUNTRIES[country])
    try:
        raw = provider.analyze(system_prompt, user_prompt, country=country)
    except NotImplementedError:
        raise AnalysisError("provider_error", "Analiz servisi henüz hazır değil.", 502)

    data = extract_json(raw)
    if data is None:
        raise AnalysisError("provider_error", "Sonuçlar şu an derlenemedi. Lütfen tekrar dene.", 502)
    if data.get("error") == "not_a_product":
        raise AnalysisError(
            "not_a_product",
            "Bu bir ürün ya da ürün kategorisi gibi görünmüyor. Satın almak istediğin şeyi yazmayı dene.",
            422,
        )
    if settings.LLM_PROVIDER == "mock":
        data = shape_for_request(data, req)
    return build_result(data, req, country)
