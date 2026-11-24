from typing import Protocol


class ProviderError(Exception):
    """The LLM provider failed (network, API error, web search unavailable...).

    The message is shown to the user, so it must be safe and in Turkish.
    Technical details go to the log, never into this message.
    """


class ProviderTimeout(ProviderError):
    """The provider did not finish within LLM_TIMEOUT_SECONDS."""


class LLMProvider(Protocol):
    def analyze(self, system_prompt: str, user_prompt: str, *, country: str, use_search: bool = True) -> str:
        """Return the model's raw text (expected to contain one JSON object).

        use_search=False is used for the cheap "repair the JSON" retry.
        """
        ...
