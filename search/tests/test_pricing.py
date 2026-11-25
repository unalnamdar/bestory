"""Price rules: mandatory price, consistent range, budget filters, evidence from real snippets."""
import json
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from pydantic import ValidationError

from search.providers.tavily_gemini_provider import EXTRA_SYSTEM_RULES
from search.services.analyzer import AnalysisError, MSG_NO_PRICES, analyze
from search.services.countries import COUNTRIES
from search.services.pricecheck import enforce_filters, parse_number, prices_in_text, verify_evidence
from search.services.prompts import SYSTEM_PROMPT
from search.services.schema import Product, SearchRequest


def req(**kw):
    return SearchRequest.model_validate({"query": "kablosuz kulaklık", **kw})


def src(url="https://shop.example/a"):
    return [{"title": "t", "url": url}]


class ParseNumberTests(SimpleTestCase):
    def test_turkish_and_english_formats(self):
        cases = {
            "1.299,00": 1299.0, "1.299": 1299.0, "1299": 1299.0, "579,90": 579.9, "579.90": 579.9,
            "1,299.00": 1299.0, "1,299": 1299.0, "12.999,50": 12999.5, "1.299.000": 1299000.0,
            "1 299": 1299.0, "1 299": 1299.0, "4,5": 4.5, "8.345": 8345.0,
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                self.assertEqual(parse_number(token), expected)

    def test_garbage_is_none(self):
        for token in ("", "abc", "1.2.x", "--"):
            with self.subTest(token=token):
                self.assertIsNone(parse_number(token))


class PricesInTextTests(SimpleTestCase):
    def test_numbers_next_to_currency_markers(self):
        text = "Xiaomi Redmi Buds 6 Play 579 TL, JBL Tune 1.469,00 ₺ ve $1,299.00 ile 12,5 EUR"
        self.assertEqual(sorted(prices_in_text(text)), [12.5, 579.0, 1299.0, 1469.0])

    def test_ratings_and_review_counts_are_not_prices(self):
        # no currency marker near the numbers
        self.assertEqual(prices_in_text("Puan 4,5 ve 8.345 değerlendirme, 24 saat pil ömrü"), [])

    def test_marker_must_be_a_word_not_part_of_a_word(self):
        self.assertEqual(prices_in_text("style 500 retry 700 entry 9"), [])
        self.assertEqual(prices_in_text("500 TRY ve 700 try"), [500.0, 700.0])


class SchemaPriceTests(SimpleTestCase):
    def product(self, **kw):
        base = {"name": "A", "sources": src()}
        base.update(kw)
        return base

    def test_price_is_required(self):
        for bad in ({}, {"price_min": None}, {"price_min": 0}, {"price_min": -5}, {"price_min": "abc"}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                Product.model_validate(self.product(**bad))

    def test_single_price_fills_price_max(self):
        p = Product.model_validate(self.product(price_min=579))
        self.assertEqual((p.price_min, p.price_max), (579, 579))

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            Product.model_validate(self.product(price_min=2000, price_max=1000))

    def test_implausibly_wide_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            Product.model_validate(self.product(price_min=500, price_max=1600))  # > 3x
        Product.model_validate(self.product(price_min=500, price_max=1500))      # exactly 3x is fine


class FilterTests(SimpleTestCase):
    def data(self, *prices):
        return {"products": [{"name": f"p{i}", "price_min": lo, "price_max": hi} for i, (lo, hi) in enumerate(prices)]}

    def test_missing_or_invalid_price_is_dropped(self):
        data = {"products": [{"name": "x"}, {"name": "y", "price_min": None}, {"name": "z", "price_min": 0},
                             {"name": "w", "price_min": "abc"}, {"name": "ok", "price_min": 10}]}
        self.assertEqual(enforce_filters(data, req()), 4)
        self.assertEqual([p["name"] for p in data["products"]], ["ok"])

    def test_max_price_is_enforced(self):
        data = self.data((1000, 1200), (1999, 2100), (2001, 2100))
        dropped = enforce_filters(data, req(filters={"max_price": 2000}))
        self.assertEqual(dropped, 1)
        self.assertEqual([p["name"] for p in data["products"]], ["p0", "p1"])  # p1 starts inside the budget

    def test_min_price_is_enforced(self):
        data = self.data((100, 200), (900, 1100), (1500, 1500))
        enforce_filters(data, req(filters={"min_price": 1000}))
        self.assertEqual([p["name"] for p in data["products"]], ["p1", "p2"])  # p1 overlaps the budget


SNIPPET = "Xiaomi Redmi Buds 6 Play 579 TL, JBL Tune T500BT 1.469,00 TL (4,5 puan, 8.345 değerlendirme)"
TEXTS = {"https://shop.example/a": SNIPPET, "https://shop.example/b": "Samsung Buds 2.999 TL ve 3.499 TL"}


def item(**kw):
    base = {"name": "Redmi", "price_min": 579, "price_max": 579, "sources": src(),
            "price_evidence": {"url": "https://shop.example/a", "quote": "Redmi Buds 6 Play 579 TL"}}
    base.update(kw)
    return base


class EvidenceTests(SimpleTestCase):
    def verify(self, *items):
        data = {"products": list(items)}
        dropped = verify_evidence(data, TEXTS)
        return data["products"], dropped

    def test_verbatim_quote_with_matching_price_passes(self):
        kept, dropped = self.verify(item())
        self.assertEqual((len(kept), dropped), (1, 0))
        self.assertEqual(kept[0]["price_source"], "shop.example")
        self.assertNotIn("price_evidence", kept[0])

    def test_quote_matching_is_case_and_whitespace_insensitive(self):
        kept, _ = self.verify(item(price_evidence={"url": "https://shop.example/a", "quote": "redmi  BUDS 6 play\n579 tl"}))
        self.assertEqual(len(kept), 1)

    def test_url_form_differences_are_tolerated(self):
        kept, _ = self.verify(item(price_evidence={"url": "https://SHOP.example/a/#x", "quote": "579 TL"}))
        self.assertEqual(len(kept), 1)

    def test_formatted_prices_match_numerically(self):
        kept, _ = self.verify(item(name="JBL", price_min=1469, price_max=1469,
                                   price_evidence={"url": "https://shop.example/a", "quote": "T500BT 1.469,00 TL"}))
        self.assertEqual(len(kept), 1)

    def test_rejections(self):
        cases = {
            "no evidence": item(price_evidence=None),
            "evidence is not a dict": item(price_evidence="579 TL"),
            "quote not in snippet": item(price_evidence={"url": "https://shop.example/a", "quote": "Redmi 499 TL"}),
            "invented url": item(price_evidence={"url": "https://other.example/x", "quote": "579 TL"}),
            "price differs from quote": item(price_min=599, price_max=599),
            "quote has no price": item(price_evidence={"url": "https://shop.example/a", "quote": "Xiaomi Redmi Buds 6 Play"}),
            "quote number without currency": item(price_min=8345, price_max=8345,
                                                  price_evidence={"url": "https://shop.example/a", "quote": "8.345 değerlendirme"}),
            "price missing": item(price_min=None),
            "tiny quote": item(price_evidence={"url": "https://shop.example/a", "quote": "5"}),
        }
        for label, bad in cases.items():
            with self.subTest(label):
                kept, dropped = self.verify(bad)
                self.assertEqual((kept, dropped), ([], 1))

    def test_price_max_must_appear_in_cited_pages(self):
        ok = item(name="Samsung", price_min=2999, price_max=3499, sources=src("https://shop.example/b"),
                  price_evidence={"url": "https://shop.example/b", "quote": "2.999 TL"})
        kept, _ = self.verify(ok)
        self.assertEqual(len(kept), 1)
        invented_max = item(name="Samsung", price_min=2999, price_max=3999, sources=src("https://shop.example/b"),
                            price_evidence={"url": "https://shop.example/b", "quote": "2.999 TL"})
        self.assertEqual(self.verify(invented_max), ([], 1))

    def test_evidence_page_is_added_as_a_source(self):
        kept, _ = self.verify(item(sources=src("https://shop.example/b")))
        urls = [s["url"] for s in kept[0]["sources"]]
        self.assertIn("https://shop.example/a", urls)
        self.assertIn("shop.example", kept[0]["sources"][-1]["title"])

    def test_mixed_batch_keeps_only_proven_products(self):
        kept, dropped = self.verify(item(name="proven"), item(name="invented", price_min=1, price_max=1))
        self.assertEqual([p["name"] for p in kept], ["proven"])
        self.assertEqual(dropped, 1)


class FakeProvider:
    """Provider that returns canned JSON and exposes the Tavily-style evidence attributes."""
    def __init__(self, data, texts=TEXTS):
        self.data = data
        self.allowed_source_urls = set(texts)
        self.source_texts = texts

    def analyze(self, system, user, *, country, use_search=True):
        return json.dumps(self.data)


@override_settings(LLM_PROVIDER="tavily_gemini")
class AnalyzerPriceTests(SimpleTestCase):
    def run_analyze(self, products, request=None):
        provider = FakeProvider({"summary": "s", "products": products})
        with mock.patch("search.services.analyzer.get_provider", return_value=provider):
            return analyze(request or req(), "TR")

    def test_only_products_with_proven_prices_are_listed(self):
        result = self.run_analyze([item(name="Gerçek"), item(name="Uydurma", price_min=1, price_max=1)])
        self.assertEqual([p["name"] for p in result["products"]], ["Gerçek"])
        product = result["products"][0]
        self.assertEqual((product["price_min"], product["price_max"]), (579, 579))
        self.assertEqual(product["price_source"], "shop.example")
        self.assertNotIn("price_evidence", product)

    def test_no_verifiable_price_gives_a_clear_error_not_an_empty_list(self):
        with self.assertRaises(AnalysisError) as ctx:
            self.run_analyze([item(price_evidence=None), item(name="b", price_min=None)])
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.message, MSG_NO_PRICES)

    def test_budget_filter_is_enforced_even_if_the_model_ignores_it(self):
        pricey = item(name="Pahalı", price_min=3000, price_max=3000,
                      price_evidence={"url": "https://shop.example/b", "quote": "Samsung Buds 2.999 TL"})
        pricey["price_min"] = pricey["price_max"] = 2999
        pricey["sources"] = src("https://shop.example/b")
        result = self.run_analyze([item(name="Ucuz"), pricey], req(filters={"max_price": 1000}))
        self.assertEqual([p["name"] for p in result["products"]], ["Ucuz"])

    def test_inconsistent_range_from_the_model_is_dropped(self):
        reversed_range = item(name="Ters", price_min=579, price_max=100)
        result = self.run_analyze([reversed_range, item(name="Tamam")])
        self.assertEqual([p["name"] for p in result["products"]], ["Tamam"])


class PromptTests(SimpleTestCase):
    def test_system_prompt_makes_price_the_top_priority(self):
        for phrase in ("PRICE RULES", "DO NOT include that product at all", "never null",
                       "Never estimate", "installment", "price_max must be >= price_min",
                       "Min price / Max price filters strictly"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, SYSTEM_PROMPT)

    def test_schema_in_prompt_has_non_nullable_prices(self):
        self.assertIn('"price_min": number,', SYSTEM_PROMPT)
        self.assertNotIn("price_min\": number|null", SYSTEM_PROMPT)
        self.assertNotIn("price_max\": number|null", SYSTEM_PROMPT)

    def test_tavily_rules_demand_a_verbatim_quote(self):
        for phrase in ("price_evidence", "EXACTLY", "removed"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, EXTRA_SYSTEM_RULES)


@override_settings(LLM_PROVIDER="mock", MOCK_DELAY_SECONDS=0, RATE_LIMIT_ANON_PER_DAY=50)
class MockStillPricedTests(TestCase):
    def test_every_mock_product_has_a_consistent_price(self):
        resp = self.client.post("/api/search/", data=json.dumps({"query": "kulaklık"}), content_type="application/json")
        products = resp.json()["data"]["products"]
        self.assertTrue(products)
        for p in products:
            self.assertGreater(p["price_min"], 0)
            self.assertGreaterEqual(p["price_max"], p["price_min"])
