"""Alineación de secuencias de palabras (programación dinámica, distancia
de Levenshtein a nivel de palabra) — la base compartida de WER, terminología
y atribución de hablante (Fase 5.1). Un único algoritmo, reutilizado por
todas las métricas que necesitan saber "qué palabra de referencia se
corresponde con qué palabra de la hipótesis", en vez de reimplementarlo
por métrica.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AlignmentOpType = Literal["match", "sub", "del", "ins"]


@dataclass(slots=True, frozen=True)
class AlignmentOp:
    op: AlignmentOpType
    ref_index: int | None
    hyp_index: int | None
    ref_word: str | None
    hyp_word: str | None


def align_words(ref_words: list[str], hyp_words: list[str]) -> list[AlignmentOp]:
    """Devuelve la secuencia de operaciones (match/sub/del/ins) que
    transforma `ref_words` en `hyp_words` con coste mínimo, en orden desde
    el principio de ambas secuencias."""
    n, m = len(ref_words), len(hyp_words)
    # dp[i][j] = coste mínimo para alinear ref_words[:i] con hyp_words[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    ops: list[AlignmentOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i - 1] == hyp_words[j - 1]:
            ops.append(
                AlignmentOp(
                    op="match",
                    ref_index=i - 1,
                    hyp_index=j - 1,
                    ref_word=ref_words[i - 1],
                    hyp_word=hyp_words[j - 1],
                )
            )
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(
                AlignmentOp(
                    op="sub",
                    ref_index=i - 1,
                    hyp_index=j - 1,
                    ref_word=ref_words[i - 1],
                    hyp_word=hyp_words[j - 1],
                )
            )
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(
                AlignmentOp(
                    op="del",
                    ref_index=i - 1,
                    hyp_index=None,
                    ref_word=ref_words[i - 1],
                    hyp_word=None,
                )
            )
            i -= 1
        else:
            ops.append(
                AlignmentOp(
                    op="ins",
                    ref_index=None,
                    hyp_index=j - 1,
                    ref_word=None,
                    hyp_word=hyp_words[j - 1],
                )
            )
            j -= 1

    ops.reverse()
    return ops
