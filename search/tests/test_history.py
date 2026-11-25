"""Profile "recent searches": stored params, distinct entries, links that hit the cache."""
import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from search.models import SearchLog
from search.services.history import recent_searches, search_url

User = get_user_model()
PROFILE = "/hesap/profil/"


def log(user, query, status="ok", country="TR", mode="value", params=None):
    return SearchLog.objects.create(user=user, ip_hash="h", query=query, country=country,
                                    mode=mode, status=status, params=params)


class SearchUrlTests(TestCase):
    def test_minimal(self):
        self.assertEqual(search_url("kulaklık", "TR", "value", {}),
                         "/?q=kulakl%C4%B1k&country=TR&mode=value")

    def test_filters_and_custom_match_search_js(self):
        url = search_url("kulaklık", "DE", "custom", {
            "filters": {"min_price": 100.0, "max_price": 2000.0, "min_rating": 4.5, "limit": 5},
            "custom_criteria": "ANC & kablosuz",
        })
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["min_price"], ["100"])  # 100.0 printed the way JavaScript does
        self.assertEqual(q["max_price"], ["2000"])
        self.assertEqual(q["min_rating"], ["4.5"])
        self.assertEqual(q["limit"], ["5"])
        self.assertEqual(q["custom"], ["ANC & kablosuz"])

    def test_default_limit_and_empty_filters_are_left_out(self):
        url = search_url("x y", "TR", "best_sellers",
                         {"filters": {"min_price": None, "max_price": None, "min_rating": None, "limit": 10},
                          "custom_criteria": ""})
        self.assertEqual(set(parse_qs(urlsplit(url).query)), {"q", "country", "mode"})

    def test_old_rows_without_params(self):
        self.assertIn("mode=value", search_url("a", "TR", "value", None))


class RecentSearchesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali", "ali@example.com", "Uzun-parola-123")
        self.other = User.objects.create_user("veli", "veli@example.com", "Uzun-parola-123")

    def test_only_own_successful_searches_newest_first(self):
        log(self.user, "eski")
        log(self.user, "hatalı", status="provider_error")
        log(self.user, "limit", status="rate_limited")
        log(self.other, "başkası")
        log(None, "anonim")
        log(self.user, "yeni")
        self.assertEqual([i["query"] for i in recent_searches(self.user)], ["yeni", "eski"])

    def test_at_most_ten_distinct(self):
        for n in range(15):
            log(self.user, f"ürün {n}")
            log(self.user, f"ÜRÜN {n}")  # same search, different case: counted once
        items = recent_searches(self.user)
        self.assertEqual(len(items), 10)
        self.assertEqual(items[0]["query"], "ÜRÜN 14")
        self.assertEqual(len({i["query"].lower() for i in items}), 10)

    def test_same_query_with_other_filters_is_separate(self):
        log(self.user, "kulaklık", params={"filters": {"limit": 10}, "custom_criteria": ""})
        log(self.user, "kulaklık", params={"filters": {"limit": 5}, "custom_criteria": ""})
        log(self.user, "kulaklık", mode="top_rated")
        self.assertEqual(len(recent_searches(self.user)), 3)

    def test_labels(self):
        log(self.user, "kulaklık", country="DE", mode="top_rated")
        item = recent_searches(self.user)[0]
        self.assertEqual(item["country_name"], "Almanya")
        self.assertEqual(item["mode_label"], "En yüksek puan")


@override_settings(LLM_PROVIDER="mock", MOCK_DELAY_SECONDS=0, RATE_LIMIT_USER_PER_DAY=20, IP_HASH_SALT="s")
class ProfileHistoryFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ali", "ali@example.com", "Uzun-parola-123")
        self.client.force_login(self.user)

    def search(self, payload):
        return self.client.post("/api/search/", data=json.dumps(payload), content_type="application/json")

    def payload_from_link(self, url):
        """What search.js sends after opening a profile link (see loadFromUrl/collect)."""
        q = parse_qs(urlsplit(url).query)
        one = lambda k: q[k][0] if k in q else None  # noqa: E731
        num = lambda k: float(one(k)) if one(k) else None  # noqa: E731
        return {
            "query": one("q"), "country": one("country"), "mode": one("mode"),
            "filters": {"min_price": num("min_price"), "max_price": num("max_price"),
                        "min_rating": num("min_rating"), "limit": int(one("limit") or 10)},
            "custom_criteria": one("custom") or "",
        }

    def test_search_stores_params_and_link_reopens_from_cache(self):
        original = {"query": "Kablosuz Kulaklık", "country": "TR", "mode": "custom",
                    "filters": {"min_price": 500, "max_price": 2000, "min_rating": 4.2, "limit": 5},
                    "custom_criteria": "ANC olsun"}
        first = self.search(original).json()
        self.assertFalse(first["cached"])

        row = SearchLog.objects.get()
        self.assertEqual(row.params["custom_criteria"], "ANC olsun")
        self.assertEqual(row.params["filters"]["limit"], 5)

        resp = self.client.get(PROFILE)
        self.assertContains(resp, "Son aramaların")
        self.assertContains(resp, "Kablosuz Kulaklık")
        link = resp.context["recent"][0]["url"]
        self.assertContains(resp, f'href="{link.replace("&", "&amp;")}"')

        again = self.search(self.payload_from_link(link)).json()
        self.assertTrue(again["cached"])  # same cache key: instant and free
        self.assertEqual(again["remaining"], first["remaining"])

    def test_empty_state(self):
        self.assertContains(self.client.get(PROFILE), "Henüz arama yapmadın")

    def test_user_text_is_escaped(self):
        log(self.user, "<script>alert(1)</script>")
        resp = self.client.get(PROFILE)
        self.assertNotContains(resp, "<script>alert(1)</script>")
        self.assertContains(resp, "&lt;script&gt;")
