"""Puerto SummaryGenerator. Ver docs/ai-pipeline-architecture.md §6.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.domain.session_context import SessionContext


@dataclass(slots=True, frozen=True)
class SummaryDraft:
    text: str


class SummaryGenerator(Protocol):
    async def generate(self, transcript: str, *, context: SessionContext) -> SummaryDraft: ...
