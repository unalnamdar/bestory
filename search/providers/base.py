from typing import Protocol


class LLMProvider(Protocol):
    def analyze(self, system_prompt: str, user_prompt: str, *, country: str) -> str:
        """Return the model's raw text (expected to contain one JSON object)."""
        ...
