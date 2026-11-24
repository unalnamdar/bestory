from django.conf import settings


def get_provider():
    """Select the LLM provider via LLM_PROVIDER (mock | anthropic | gemini | tavily_gemini)."""
    name = getattr(settings, "LLM_PROVIDER", "mock")
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    if name == "tavily_gemini":
        from .tavily_gemini_provider import TavilyGeminiProvider
        return TavilyGeminiProvider()
    raise ValueError(f"Unknown LLM_PROVIDER={name!r} (use 'mock', 'anthropic', 'gemini' or 'tavily_gemini').")
