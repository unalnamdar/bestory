"""Run ONE real analysis with the provider selected in .env and print the result.

Usage (costs real money, roughly 0.1-0.3 USD with web search):
    .venv\\Scripts\\python.exe live_check.py
    .venv\\Scripts\\python.exe live_check.py "robot süpürge" US value

It calls the analyzer directly: nothing is written to the database (no cache, no
SearchLog, no rate limit), and API keys are never printed.
"""
import logging
import os
import sys
import time
from urllib.parse import urlparse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bestory.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from search.services.analyzer import AnalysisError, analyze  # noqa: E402
from search.services.schema import SearchRequest  # noqa: E402

logging.basicConfig(level=logging.INFO, format="  [log] %(name)s: %(message)s")

query = sys.argv[1] if len(sys.argv) > 1 else "kablosuz kulaklık"
country = (sys.argv[2] if len(sys.argv) > 2 else "TR").upper()
mode = sys.argv[3] if len(sys.argv) > 3 else "value"

if settings.LLM_PROVIDER == "mock":
    sys.exit("LLM_PROVIDER is 'mock'. Set LLM_PROVIDER=anthropic or gemini (and the API key) in .env first.")

model = settings.ANTHROPIC_MODEL if settings.LLM_PROVIDER == "anthropic" else settings.GEMINI_MODEL  # tavily_gemini uses Gemini
print(f"Provider: {settings.LLM_PROVIDER}  model: {model}  timeout: {settings.LLM_TIMEOUT_SECONDS}s")
print(f"Search:   {query!r}  country={country}  mode={mode}\n")

req = SearchRequest.model_validate({"query": query, "country": country, "mode": mode, "filters": {"limit": 10}})

started = time.monotonic()
try:
    data = analyze(req, country)
except AnalysisError as exc:
    print(f"\nFAILED after {time.monotonic() - started:.1f}s: [{exc.status}] {exc.code}: {exc.message}")
    sys.exit(1)
elapsed = time.monotonic() - started

print(f"\nOK in {elapsed:.1f}s - {len(data['products'])} valid product(s)")
print(f"summary: {data['summary']}\n")
for p in data["products"]:
    price = f"{p['price_min']}-{p['price_max']} {data['currency']}" if p["price_min"] is not None else "no price"
    rating = f"{p['rating']} ({p['rating_count']} reviews, {p['rating_source']})" if p["rating"] is not None else "no rating"
    domains = ", ".join(urlparse(s["url"]).netloc for s in p["sources"])
    print(f"{p['rank']:>2}. {p['name']}  |  {price}  |  {rating}")
    print(f"      sources: {domains}")
print("\nFull JSON saved to live_check_output.json")

import json  # noqa: E402

with open("live_check_output.json", "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
