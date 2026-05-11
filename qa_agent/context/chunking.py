"""Prompt-safe chunking helpers.

Splits long text into chunks bounded by a character cap (configured at
`llm.prompt_char_cap` — default 4096). Tries to break on paragraph or
sentence boundaries before falling back to a hard cut.
"""

from __future__ import annotations

import re
from typing import Iterable

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def chunk(text: str, max_chars: int) -> list[str]:
    """Return text chunks each <= max_chars."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return [text]

    out: list[str] = []
    for para in _split_paragraphs(text):
        if len(para) <= max_chars:
            out.append(para)
            continue
        out.extend(_split_long(para, max_chars))
    return _merge_small(out, max_chars)


def _split_paragraphs(text: str) -> Iterable[str]:
    for raw in text.split("\n\n"):
        p = raw.strip()
        if p:
            yield p


def _split_long(text: str, max_chars: int) -> list[str]:
    sents = _SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for s in sents:
        slen = len(s) + 1
        if size + slen > max_chars and buf:
            chunks.append(" ".join(buf))
            buf, size = [], 0
        if slen > max_chars:
            # hard cut very long sentence
            for i in range(0, len(s), max_chars):
                chunks.append(s[i : i + max_chars])
            continue
        buf.append(s)
        size += slen
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def _merge_small(chunks: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    for c in chunks:
        if out and len(out[-1]) + 2 + len(c) <= max_chars:
            out[-1] = f"{out[-1]}\n\n{c}"
        else:
            out.append(c)
    return out
