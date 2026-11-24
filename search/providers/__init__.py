from django.conf import settings


def get_provider():
    """Select the LLM provider via LLM_PROVIDER (mock | anthropic)."""
    name = getattr(settings, "LLM_PROVIDER", "mock")
    if name == "mock":
        from .mock import MockProvider
        return MockProvider()
    raise NotImplementedError(f"LLM_PROVIDER={name!r} is not implemented yet (Phase 2).")
