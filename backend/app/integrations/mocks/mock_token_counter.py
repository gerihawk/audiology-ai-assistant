"""MockTokenCounter: heurística simple de recuento de palabras, sin dependencia externa."""

from __future__ import annotations


class MockTokenCounter:
    def count(self, text: str, *, model: str | None = None) -> int:
        return len(text.split())
