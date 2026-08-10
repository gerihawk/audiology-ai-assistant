"""Puerto TokenCounter. Ver docs/ai-pipeline-architecture.md §6.1."""

from __future__ import annotations

from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str, *, model: str | None = None) -> int: ...
