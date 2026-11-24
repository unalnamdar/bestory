"""Minimal Tavily Search client (standard library only, no extra dependency).

Verified against https://docs.tavily.com/documentation/api-reference/endpoint/search
on 2026-11-24: POST https://api.tavily.com/search, `Authorization: Bearer <key>`,
JSON body, `country` is a lowercase country name and only works with topic=general.
Errors come back as {"detail": {"error": "..."}} with 401 (bad key), 429 (rate limit),
432/433 (plan or pay-as-you-go limit exceeded), 5xx.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from .base import ProviderError, ProviderTimeout

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.tavily.com/search"
MSG_NO_SEARCH = "Web araması şu an kullanılamıyor. Lütfen biraz sonra tekrar dene."
MSG_TIMEOUT = "Analiz beklenenden uzun sürdü. Lütfen tekrar dene."


class TavilyClient:
    def __init__(self, api_key=None):
        self.api_key = api_key if api_key is not None else settings.TAVILY_API_KEY
        if not self.api_key:
            logger.error("TAVILY_API_KEY is empty")
            raise ProviderError(MSG_NO_SEARCH)

    def search(self, query, *, country_name=None, max_results=8, timeout=20, include_domains=None):
        """Run one basic search (1 credit). Returns the list of result dicts.

        include_domains is sent with include_domains_mode="prefer": results from those sites are
        favoured but other sites can still appear ("restrict" would return nothing for thin queries).
        """
        body = {
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": max_results,
        }
        if country_name:
            body["country"] = country_name
        if include_domains:
            body["include_domains"] = list(include_domains)
            body["include_domains_mode"] = "prefer"
        request = urllib.request.Request(
            SEARCH_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = str(json.loads(exc.read().decode("utf-8")).get("detail", ""))[:200]
            except Exception:
                pass
            # 401 bad key, 429 rate limit, 432/433 credit limits: details go to the log only.
            logger.error("Tavily HTTP %s: %s", exc.code, detail)
            raise ProviderError(MSG_NO_SEARCH)
        except TimeoutError:
            raise ProviderTimeout(MSG_TIMEOUT)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ProviderTimeout(MSG_TIMEOUT)
            logger.error("Tavily connection error: %s", type(exc.reason).__name__)
            raise ProviderError(MSG_NO_SEARCH)
        except (ValueError, UnicodeDecodeError):
            logger.error("Tavily returned a non-JSON response")
            raise ProviderError(MSG_NO_SEARCH)

        usage = payload.get("usage") or {}
        logger.info("tavily search credits=%s results=%s", usage.get("credits"), len(payload.get("results") or []))
        results = payload.get("results")
        return results if isinstance(results, list) else []
