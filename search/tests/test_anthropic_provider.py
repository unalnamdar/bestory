"""AnthropicProvider with a fake client: never touches the network or an API key."""
from types import SimpleNamespace as NS

import anthropic
import httpx2
from django.test import SimpleTestCase, override_settings

from search.providers.anthropic_provider import AnthropicProvider, MAX_PAUSE_CONTINUATIONS
from search.providers.base import ProviderError, ProviderTimeout

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def text(t):
    return NS(type="text", text=t)


def search_ok():
    return NS(type="web_search_tool_result", content=[NS(type="web_search_result", url="https://example.com")])


def search_error(code="unavailable"):
    return NS(type="web_search_tool_result", content=NS(type="web_search_tool_result_error", error_code=code))


def response(content, stop="end_turn"):
    return NS(content=content, stop_reason=stop,
              usage=NS(input_tokens=10, output_tokens=5, server_tool_use=NS(web_search_requests=1)))


class FakeClient:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@override_settings(ANTHROPIC_MODEL="claude-sonnet-5-5", LLM_MAX_SEARCHES=5, LLM_TIMEOUT_SECONDS=90, ANTHROPIC_API_KEY="test")
class AnthropicProviderTests(SimpleTestCase):
    def run_provider(self, *outcomes, **kw):
        client = FakeClient(*outcomes)
        out = AnthropicProvider(client=client).analyze("sys", "usr", country=kw.pop("country", "TR"), **kw)
        return out, client

    def test_request_uses_web_search_tool_model_and_location(self):
        out, client = self.run_provider(response([search_ok(), text('{"a": 1}')]))
        call = client.calls[0]
        self.assertEqual(call["model"], "claude-sonnet-5-5")
        self.assertEqual(call["system"], "sys")
        self.assertEqual(call["messages"], [{"role": "user", "content": "usr"}])
        tool = call["tools"][0]
        self.assertEqual(tool["type"], "web_search_20250305")
        self.assertEqual(tool["name"], "web_search")
        self.assertEqual(tool["max_uses"], 5)
        self.assertEqual(tool["user_location"], {"type": "approximate", "country": "TR", "timezone": "Europe/Istanbul"})
        self.assertEqual(out, '{"a": 1}')

    def test_user_location_follows_country(self):
        _, client = self.run_provider(response([text("{}")]), country="DE")
        self.assertEqual(client.calls[0]["tools"][0]["user_location"]["country"], "DE")

    def test_text_blocks_are_joined(self):
        out, _ = self.run_provider(response([text('{"a":'), search_ok(), text(' 1}')]))
        self.assertEqual(out, '{"a": 1}')

    def test_no_search_tool_for_repair_call(self):
        _, client = self.run_provider(response([text("{}")]), use_search=False)
        self.assertNotIn("tools", client.calls[0])

    def test_pause_turn_continues_with_same_tools_and_assistant_content(self):
        paused = response([search_ok(), text("partial")], stop="pause_turn")
        out, client = self.run_provider(paused, response([text('{"done": true}')]))
        self.assertEqual(len(client.calls), 2)
        second = client.calls[1]
        self.assertEqual(second["tools"], client.calls[0]["tools"])
        self.assertEqual(second["messages"][-1], {"role": "assistant", "content": paused.content})
        self.assertEqual(out, '{"done": true}')

    def test_pause_turn_is_capped(self):
        paused = [response([text("x")], stop="pause_turn") for _ in range(MAX_PAUSE_CONTINUATIONS + 1)]
        client = FakeClient(*paused)
        with self.assertRaises(ProviderError):
            AnthropicProvider(client=client).analyze("s", "u", country="TR")
        self.assertEqual(len(client.calls), MAX_PAUSE_CONTINUATIONS + 1)

    def test_all_searches_failing_raises_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(response([search_error("max_uses_exceeded"), text("{}")]))
        self.assertIn("Web araması", str(ctx.exception))

    def test_partial_search_failure_still_returns_text(self):
        out, _ = self.run_provider(response([search_error("too_many_requests"), search_ok(), text('{"ok": 1}')]))
        self.assertEqual(out, '{"ok": 1}')

    def test_timeout_maps_to_provider_timeout(self):
        with self.assertRaises(ProviderTimeout):
            self.run_provider(anthropic.APITimeoutError(request=REQUEST))

    def test_api_status_error_hides_details(self):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "web search is not enabled secret-detail"}}
        exc = anthropic.BadRequestError("web search is not enabled secret-detail",
                                        response=httpx2.Response(400, request=REQUEST), body=body)
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(exc)
        self.assertNotIn("secret-detail", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, ProviderTimeout)

    def test_connection_error_maps_to_provider_error(self):
        with self.assertRaises(ProviderError):
            self.run_provider(anthropic.APIConnectionError(request=REQUEST))

    def test_per_call_timeout_never_exceeds_configured_limit(self):
        _, client = self.run_provider(response([text("{}")]))
        self.assertLessEqual(client.calls[0]["timeout"], 90)
        self.assertGreater(client.calls[0]["timeout"], 80)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_missing_api_key_is_provider_error(self):
        with self.assertRaises(ProviderError):
            AnthropicProvider()
