"""Google Gemini (Interactions API) with the built-in Google Search tool.

Checked on 2026-11-24 against https://aistudio.google.com/docs/google-search (moved from
ai.google.dev) and against the installed google-genai SDK:
- `client.interactions.create(model=, input=, system_instruction=, tools=[{"type": "google_search"}])`
- a numeric `timeout` (seconds) is a wall-clock budget for the whole call
- `store=False` so Google does not keep the conversation
- there is NO option to cap the number of searches or to bias by country, so
  LLM_MAX_SEARCHES is only passed as a soft instruction and the country is given in the prompt
- structured output can be combined with google_search only on Gemini 3/4 models; to stay
  model-independent, JSON is requested through the prompt and extracted/validated by the analyzer.
"""
import logging
import time

from django.conf import settings
from google import genai
from google.genai import errors, types

from .base import ProviderError, ProviderTimeout

logger = logging.getLogger(__name__)

REPAIR_TIMEOUT_SECONDS = 30
OVERLOAD_STATUS_CODES = (500, 502, 503, 504)  # temporary Google-side errors: retried once
OVERLOAD_RETRY_DELAY_SECONDS = 2

MSG_UNAVAILABLE = "Analiz servisine şu an ulaşılamıyor. Lütfen biraz sonra tekrar dene."
MSG_BUSY = "Analiz servisi şu an çok yoğun. Birkaç dakika sonra tekrar dene."
MSG_NO_SEARCH = "Web araması şu an kullanılamıyor. Lütfen biraz sonra tekrar dene."
MSG_TIMEOUT = "Analiz beklenenden uzun sürdü. Lütfen tekrar dene."

# Network-level timeouts raised by the HTTP layer on the first hop.
_TIMEOUT_NAMES = {"TimeoutException", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout", "APITimeoutError"}


def _is_timeout(exc):
    return isinstance(exc, TimeoutError) or type(exc).__name__ in _TIMEOUT_NAMES


class GeminiProvider:
    def __init__(self, client=None):
        if client is None:
            if not settings.GEMINI_API_KEY:
                logger.error("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty")
                raise ProviderError(MSG_UNAVAILABLE)
            # attempts=1: no SDK-level retries. Retrying quota errors is pointless and the
            # SDK backoff (5 attempts) pushed one request to 123 s, past LLM_TIMEOUT_SECONDS.
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
            )
        self.client = client

    def analyze(self, system_prompt, user_prompt, *, country, use_search=True, timeout=None):
        request = {
            "model": settings.GEMINI_MODEL,
            "input": user_prompt,
            "system_instruction": system_prompt,
            "store": False,
            "timeout": timeout or (settings.LLM_TIMEOUT_SECONDS if use_search else REPAIR_TIMEOUT_SECONDS),
        }
        if use_search:
            request["tools"] = [{"type": "google_search"}]
            request["system_instruction"] = (
                f"{system_prompt}\nUse at most {settings.LLM_MAX_SEARCHES} web search queries in total."
            )

        total = request["timeout"]
        deadline = time.monotonic() + total
        # Same model twice (brief "high demand" spikes), then the fallback model once.
        fallback = getattr(settings, "GEMINI_FALLBACK_MODEL", "")
        models = [request["model"], request["model"]]
        if fallback and fallback != request["model"]:
            models.append(fallback)

        interaction = None
        for attempt, model in enumerate(models, start=1):
            request["model"] = model
            request["timeout"] = max(1, deadline - time.monotonic())
            try:
                interaction = self.client.interactions.create(**request)
                if attempt > 1:
                    logger.info("Gemini succeeded on attempt %s with model %s", attempt, model)
                break
            except errors.ContinuationInterruptedError as exc:
                if _is_timeout(exc.__cause__):
                    raise ProviderTimeout(MSG_TIMEOUT)
                logger.error("Gemini continuation interrupted: %s", type(exc.__cause__).__name__)
                raise ProviderError(MSG_UNAVAILABLE)
            except Exception as exc:  # APIError (generateContent style), Interactions API errors, network...
                if _is_timeout(exc):
                    raise ProviderTimeout(MSG_TIMEOUT)
                # The Interactions API raises its own error classes (e.g. RateLimitError) from a
                # private module, so they are recognised by their HTTP status code instead.
                status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                logger.error("Gemini request failed (attempt %s, %s): %s status=%s message=%s", attempt, model,
                             type(exc).__name__, status_code, str(getattr(exc, "message", ""))[:300])
                overloaded = status_code in OVERLOAD_STATUS_CODES
                has_next = attempt < len(models)
                if overloaded and has_next and deadline - time.monotonic() > OVERLOAD_RETRY_DELAY_SECONDS + 10:
                    if attempt == 1:
                        time.sleep(OVERLOAD_RETRY_DELAY_SECONDS)  # spikes are usually brief
                    continue
                raise ProviderError(MSG_BUSY if status_code == 429 else MSG_UNAVAILABLE)

        status = getattr(interaction, "status", None)
        # "incomplete" (e.g. output token limit) still has text; the analyzer's JSON
        # extraction/repair decides if it is usable. Anything else but "completed" is a failure.
        if status not in ("completed", "incomplete"):
            logger.error("Gemini interaction ended with status=%s", status)
            raise ProviderError(MSG_UNAVAILABLE)

        ok, failed = self._count_searches(interaction)
        self._log_usage(interaction, ok, failed)
        if failed and ok == 0:
            raise ProviderError(MSG_NO_SEARCH)

        return self._text(interaction)

    @staticmethod
    def _text(interaction):
        parts = []
        for step in getattr(interaction, "steps", None) or []:
            if getattr(step, "type", "") != "model_output":
                continue  # skip thoughts and tool calls
            for block in getattr(step, "content", None) or []:
                if getattr(block, "type", "") == "text":
                    parts.append(block.text or "")
        return "".join(parts)

    @staticmethod
    def _count_searches(interaction):
        ok = failed = 0
        for step in getattr(interaction, "steps", None) or []:
            if getattr(step, "type", "") == "google_search_result":
                if getattr(step, "is_error", False):
                    failed += 1
                else:
                    ok += 1
        return ok, failed

    @staticmethod
    def _log_usage(interaction, ok, failed):
        usage = getattr(interaction, "usage", None)
        logger.info(
            "gemini usage input=%s output=%s grounding=%s searches_ok=%s searches_failed=%s",
            getattr(usage, "total_input_tokens", None),
            getattr(usage, "total_output_tokens", None),
            getattr(usage, "grounding_tool_count", None),
            ok, failed,
        )
