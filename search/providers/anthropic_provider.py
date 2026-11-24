"""Anthropic Messages API + server-side web search tool.

Verified against the docs on 2026-11-24:
https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- tool type `web_search_20250305` (basic; the newer versions add dynamic filtering,
  which needs code execution and is not needed here)
- web search errors come back inside an HTTP 200 as `web_search_tool_result_error`
- `pause_turn`: send the paused assistant content back unchanged to continue
- the docs do not confirm structured outputs together with web search, so JSON is
  requested through the prompt and extracted/validated by the analyzer.
"""
import logging
import time

import anthropic
from django.conf import settings

from ..services.countries import COUNTRIES
from .base import ProviderError, ProviderTimeout

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_TYPE = "web_search_20250305"
MAX_PAUSE_CONTINUATIONS = 2
MAX_TOKENS = 8000
REPAIR_TIMEOUT_SECONDS = 30  # the repair retry uses no search, so it is quick

MSG_UNAVAILABLE = "Analiz servisine şu an ulaşılamıyor. Lütfen biraz sonra tekrar dene."
MSG_NO_SEARCH = "Web araması şu an kullanılamıyor. Lütfen biraz sonra tekrar dene."
MSG_TIMEOUT = "Analiz beklenenden uzun sürdü. Lütfen tekrar dene."


class AnthropicProvider:
    def __init__(self, client=None):
        if client is None:
            if not settings.ANTHROPIC_API_KEY:
                logger.error("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
                raise ProviderError(MSG_UNAVAILABLE)
            # max_retries=0: total time is bounded by our own deadline instead.
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=0)
        self.client = client

    @staticmethod
    def build_tool(country):
        tool = {
            "type": WEB_SEARCH_TOOL_TYPE,
            "name": "web_search",
            "max_uses": settings.LLM_MAX_SEARCHES,
        }
        info = COUNTRIES.get(country)
        if info:
            tool["user_location"] = {
                "type": "approximate",
                "country": country,
                "timezone": info["timezone"],
            }
        return tool

    def analyze(self, system_prompt, user_prompt, *, country, use_search=True):
        total = settings.LLM_TIMEOUT_SECONDS if use_search else REPAIR_TIMEOUT_SECONDS
        deadline = time.monotonic() + total
        request = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
        }
        if use_search:
            request["tools"] = [self.build_tool(country)]

        messages = [{"role": "user", "content": user_prompt}]
        searches_ok = 0
        search_errors = []

        for attempt in range(MAX_PAUSE_CONTINUATIONS + 1):
            remaining = deadline - time.monotonic()
            if remaining < 1:
                raise ProviderTimeout(MSG_TIMEOUT)
            try:
                response = self.client.messages.create(messages=messages, timeout=remaining, **request)
            except anthropic.APITimeoutError:
                raise ProviderTimeout(MSG_TIMEOUT)
            except anthropic.APIStatusError as exc:
                # Includes 400 "web search is not enabled" for the organization.
                logger.error("Anthropic API error status=%s body=%s", exc.status_code, getattr(exc, "message", ""))
                raise ProviderError(MSG_UNAVAILABLE)
            except anthropic.APIError as exc:
                logger.error("Anthropic connection error: %s", type(exc).__name__)
                raise ProviderError(MSG_UNAVAILABLE)

            ok, errors = self._inspect_search_results(response)
            searches_ok += ok
            search_errors += errors
            self._log_usage(response)

            if response.stop_reason != "pause_turn":
                break
            if attempt == MAX_PAUSE_CONTINUATIONS:
                logger.error("Still pause_turn after %s continuations", MAX_PAUSE_CONTINUATIONS)
                raise ProviderError(MSG_UNAVAILABLE)
            # Continue: send the paused assistant content back unchanged.
            messages = messages + [{"role": "assistant", "content": response.content}]

        if search_errors and searches_ok == 0:
            logger.error("All web searches failed: %s", search_errors)
            raise ProviderError(MSG_NO_SEARCH)
        if search_errors:
            logger.warning("Some web searches failed: %s", search_errors)

        return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")

    @staticmethod
    def _inspect_search_results(response):
        ok, errors = 0, []
        for block in response.content:
            if getattr(block, "type", "") != "web_search_tool_result":
                continue
            content = block.content
            if getattr(content, "type", "") == "web_search_tool_result_error":
                errors.append(getattr(content, "error_code", "unknown"))
            else:
                ok += 1
        return ok, errors

    @staticmethod
    def _log_usage(response):
        usage = getattr(response, "usage", None)
        if not usage:
            return
        server_tool = getattr(usage, "server_tool_use", None)
        logger.info(
            "anthropic usage input=%s output=%s web_searches=%s stop=%s",
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(server_tool, "web_search_requests", None) if server_tool else None,
            response.stop_reason,
        )
