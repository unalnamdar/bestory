"""Mock provider: returns a fixture, no network and no API key needed."""
import copy
import json
import time
from pathlib import Path

from django.conf import settings

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "mock_wireless_headphones_tr.json"

# Typing one of these words returns not_a_product (lets the UI error state be tried).
NOT_A_PRODUCT_WORDS = ("şiir", "siir", "poem", "hikaye", "fıkra")


class MockProvider:
    def analyze(self, system_prompt, user_prompt, *, country):
        time.sleep(getattr(settings, "MOCK_DELAY_SECONDS", 1.5))  # fake latency
        lowered = user_prompt.lower()
        query_part = lowered.split("<user_query>")[-1].split("</user_query>")[0]
        if any(word in query_part for word in NOT_A_PRODUCT_WORDS):
            return json.dumps({"error": "not_a_product"})
        return FIXTURE.read_text(encoding="utf-8")


def shape_for_request(data, req):
    """Make the static fixture react to mode and filters so the UI feels real.

    Mock only: a real provider is asked to apply these rules itself.
    """
    f = req.filters
    products = copy.deepcopy(data.get("products", []))

    def price(p):
        return p.get("price_min")

    if f.min_price is not None:
        products = [p for p in products if price(p) is None or (p.get("price_max") or price(p)) >= f.min_price]
    if f.max_price is not None:
        products = [p for p in products if price(p) is None or price(p) <= f.max_price]

    min_rating = f.min_rating
    if req.mode == "value" and min_rating is None:
        min_rating = 4.0
    if min_rating is not None:
        products = [p for p in products if (p.get("rating") or 0) >= min_rating]

    if req.mode == "top_rated":
        products = [p for p in products if (p.get("rating_count") or 0) >= 50]
        products.sort(key=lambda p: (-(p.get("rating") or 0), -(p.get("rating_count") or 0)))
    elif req.mode == "value":
        products.sort(key=lambda p: -(p.get("value_score") or 0))
    # best_sellers / custom keep the fixture's own order.

    data = dict(data)
    data["products"] = products
    return data
