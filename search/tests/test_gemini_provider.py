"""GeminiProvider with a fake client: never touches the network or an API key."""
from types import SimpleNamespace as NS

import httpx2
from django.test import SimpleTestCase, TestCase, override_settings
from google.genai import errors

from search.providers import get_provider
from search.providers.base import ProviderError, ProviderTimeout
from search.providers.gemini_provider import GeminiProvider
from search.providers.mock import MockProvider


def text_step(*texts):
    return NS(type="model_output", content=[NS(type="text", text=t, annotations=[]) for t in texts])


def thought():
    return NS(type="thought", content=[NS(type="text", text="THINKING SECRET")])


def search_call():
    return NS(type="google_search_call", arguments={"queries": ["x"]})


def search_result(is_error=False):
    return NS(type="google_search_result", is_error=is_error, result=[])


def interaction(steps, status="completed"):
    return NS(status=status, steps=steps, usage=NS(total_input_tokens=10, total_output_tokens=5, grounding_tool_count=1))


class FakeInteractions:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes):
        self.interactions = FakeInteractions(*outcomes)


@override_settings(GEMINI_MODEL="gemini-3.5-flash-lite", GEMINI_FALLBACK_MODEL="", GEMINI_API_KEY="test",
                   LLM_TIMEOUT_SECONDS=90, LLM_MAX_SEARCHES=5)
class GeminiProviderTests(SimpleTestCase):
    def run_provider(self, *outcomes, **kw):
        client = FakeClient(*outcomes)
        out = GeminiProvider(client=client).analyze("sys", "usr", country="TR", **kw)
        return out, client.interactions.calls

    def test_request_shape(self):
        out, calls = self.run_provider(interaction([search_call(), search_result(), text_step('{"a": 1}')]))
        call = calls[0]
        self.assertEqual(call["model"], "gemini-3.5-flash-lite")
        self.assertEqual(call["input"], "usr")
        self.assertTrue(call["system_instruction"].startswith("sys"))
        self.assertIn("at most 5 web search", call["system_instruction"])
        self.assertEqual(call["tools"], [{"type": "google_search"}])
        self.assertIs(call["store"], False)  # do not let Google keep the conversation
        self.assertEqual(call["timeout"], 90)
        self.assertEqual(out, '{"a": 1}')

    def test_repair_call_has_no_search_and_short_timeout(self):
        _, calls = self.run_provider(interaction([text_step("{}")]), use_search=False)
        self.assertNotIn("tools", calls[0])
        self.assertEqual(calls[0]["system_instruction"], "sys")
        self.assertLessEqual(calls[0]["timeout"], 30)

    def test_only_model_output_text_is_returned(self):
        steps = [thought(), search_call(), search_result(), text_step('{"a":', " 1}"), thought()]
        out, _ = self.run_provider(interaction(steps))
        self.assertEqual(out, '{"a": 1}')
        self.assertNotIn("SECRET", out)

    def test_all_searches_failing_is_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(interaction([search_result(is_error=True), text_step("{}")]))
        self.assertIn("Web araması", str(ctx.exception))

    def test_partial_search_failure_still_returns_text(self):
        out, _ = self.run_provider(interaction([search_result(is_error=True), search_result(), text_step("{}")]))
        self.assertEqual(out, "{}")

    def test_incomplete_status_still_returns_text_for_repair(self):
        out, _ = self.run_provider(interaction([text_step('{"cut": ')], status="incomplete"))
        self.assertEqual(out, '{"cut": ')

    def test_failed_status_is_provider_error(self):
        for status in ("failed", "cancelled", "budget_exceeded", "in_progress"):
            with self.subTest(status=status), self.assertRaises(ProviderError):
                self.run_provider(interaction([text_step("{}")], status=status))

    def test_api_error_hides_details(self):
        exc = errors.ClientError(400, {"error": {"message": "secret-detail free tier grounding", "status": "INVALID_ARGUMENT"}})
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(exc)
        self.assertNotIn("secret-detail", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, ProviderTimeout)

    def test_quota_error_gets_busy_message(self):
        exc = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(exc)
        self.assertIn("yoğun", str(ctx.exception))

    def test_server_error_maps_to_provider_error(self):
        with self.assertRaises(ProviderError):
            self.run_provider(errors.ServerError(503, {"error": {"message": "down"}}))

    def test_timeouts_map_to_provider_timeout(self):
        interrupted = errors.ContinuationInterruptedError("budget used up")
        interrupted.__cause__ = TimeoutError()
        request = httpx2.Request("POST", "https://example.com")
        for exc in (interrupted, TimeoutError(), httpx2.ReadTimeout("slow", request=request)):
            with self.subTest(exc=type(exc).__name__), self.assertRaises(ProviderTimeout):
                self.run_provider(exc)

    def test_interrupted_without_timeout_is_provider_error(self):
        interrupted = errors.ContinuationInterruptedError("network dropped")
        interrupted.__cause__ = ConnectionError()
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(interrupted)
        self.assertNotIsInstance(ctx.exception, ProviderTimeout)

    def test_interactions_rate_limit_error_by_status_code(self):
        # The Interactions API raises private RateLimitError classes with status_code=429.
        class RateLimitError(Exception):
            status_code = 429
            message = "You exceeded your current quota, please check your plan and billing details."
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(RateLimitError())
        self.assertIn("yoğun", str(ctx.exception))
        self.assertNotIn("quota", str(ctx.exception))

    def test_interactions_timeout_class_is_timeout(self):
        class APITimeoutError(Exception):
            pass
        with self.assertRaises(ProviderTimeout):
            self.run_provider(APITimeoutError())

    def test_overload_503_is_retried_once_then_succeeds(self):
        from unittest import mock
        with mock.patch("search.providers.gemini_provider.time.sleep") as sleep:
            out, calls = self.run_provider(errors.ServerError(503, {"error": {"message": "high demand"}}),
                                           interaction([text_step('{"ok": 1}')]))
        self.assertEqual(out, '{"ok": 1}')
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once()

    def test_overload_503_gives_up_after_one_retry(self):
        from unittest import mock
        client = FakeClient(errors.ServerError(503, {"error": {"message": "a"}}),
                            errors.ServerError(503, {"error": {"message": "b"}}))
        with mock.patch("search.providers.gemini_provider.time.sleep"), self.assertRaises(ProviderError):
            GeminiProvider(client=client).analyze("s", "u", country="TR")
        self.assertEqual(len(client.interactions.calls), 2)

    @override_settings(GEMINI_FALLBACK_MODEL="gemini-3.6-flash")
    def test_falls_back_to_second_model_after_two_overloads(self):
        from unittest import mock
        overload = lambda: errors.ServerError(503, {"error": {"message": "high demand"}})
        with mock.patch("search.providers.gemini_provider.time.sleep") as sleep:
            out, calls = self.run_provider(overload(), overload(), interaction([text_step('{"fb": 1}')]))
        self.assertEqual(out, '{"fb": 1}')
        self.assertEqual([c["model"] for c in calls], ["gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.6-flash"])
        sleep.assert_called_once()  # only between the two tries of the main model

    @override_settings(GEMINI_FALLBACK_MODEL="gemini-3.6-flash")
    def test_all_models_overloaded_is_provider_error(self):
        from unittest import mock
        client = FakeClient(*[errors.ServerError(503, {"error": {"message": "x"}}) for _ in range(3)])
        with mock.patch("search.providers.gemini_provider.time.sleep"), self.assertRaises(ProviderError):
            GeminiProvider(client=client).analyze("s", "u", country="TR")
        self.assertEqual(len(client.interactions.calls), 3)

    @override_settings(GEMINI_FALLBACK_MODEL="gemini-3.6-flash")
    def test_fallback_is_not_used_for_quota_errors(self):
        client = FakeClient(errors.ClientError(429, {"error": {"message": "quota"}}))
        with self.assertRaises(ProviderError):
            GeminiProvider(client=client).analyze("s", "u", country="TR")
        self.assertEqual(len(client.interactions.calls), 1)

    def test_quota_and_client_errors_are_not_retried(self):
        for code in (400, 401, 429):
            client = FakeClient(errors.ClientError(code, {"error": {"message": "x"}}))
            with self.subTest(code=code), self.assertRaises(ProviderError):
                GeminiProvider(client=client).analyze("s", "u", country="TR")
            self.assertEqual(len(client.interactions.calls), 1)

    def test_retry_uses_remaining_time_budget(self):
        from unittest import mock
        with mock.patch("search.providers.gemini_provider.time.sleep"):
            _, calls = self.run_provider(errors.ServerError(503, {"error": {"message": "x"}}),
                                         interaction([text_step("{}")]))
        self.assertLessEqual(calls[1]["timeout"], calls[0]["timeout"])

    def test_unexpected_exception_is_provider_error(self):
        with self.assertRaises(ProviderError):
            self.run_provider(RuntimeError("boom secret-detail"))

    @override_settings(GEMINI_API_KEY="")
    def test_missing_api_key_is_provider_error(self):
        with self.assertRaises(ProviderError):
            GeminiProvider()

    def test_client_is_built_without_sdk_retries(self):
        from unittest import mock
        with mock.patch("search.providers.gemini_provider.genai.Client") as client_cls:
            GeminiProvider()
        http_options = client_cls.call_args.kwargs["http_options"]
        self.assertEqual(http_options.retry_options.attempts, 1)


class ProviderSelectionTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="mock")
    def test_mock(self):
        self.assertIsInstance(get_provider(), MockProvider)

    @override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="test")
    def test_gemini(self):
        self.assertIsInstance(get_provider(), GeminiProvider)

    @override_settings(LLM_PROVIDER="nope")
    def test_unknown_provider_fails_loudly(self):
        with self.assertRaises(ValueError):
            get_provider()


@override_settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="", RATE_LIMIT_ANON_PER_DAY=5)
class GeminiEndToEndTests(TestCase):
    def test_gemini_without_key_is_clean_502_and_hides_setting_names(self):
        import json
        resp = self.client.post("/api/search/", data=json.dumps({"query": "kablosuz kulaklık"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 502)
        self.assertNotIn("GEMINI", resp.content.decode())

    def test_full_flow_with_fake_gemini_client(self):
        import json
        from unittest import mock
        good = json.dumps({"summary": "özet", "products": [
            {"name": "Ürün A", "price_min": 100, "sources": [{"title": "t", "url": "https://example.com/a"}]},
            {"name": "Kaynaksız", "sources": []},
        ]})
        client = FakeClient(interaction([search_call(), search_result(), text_step(good)]))
        with override_settings(GEMINI_API_KEY="test"), \
                mock.patch("search.providers.gemini_provider.genai.Client", return_value=client):
            first = self.client.post("/api/search/", data=json.dumps({"query": "gemini deneme", "country": "TR"}),
                                     content_type="application/json")
            second = self.client.post("/api/search/", data=json.dumps({"query": "gemini deneme", "country": "TR"}),
                                      content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual([p["name"] for p in first.json()["data"]["products"]], ["Ürün A"])
        self.assertTrue(second.json()["cached"])
        self.assertEqual(len(client.interactions.calls), 1)  # second request came from cache
