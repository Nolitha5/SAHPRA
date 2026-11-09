"""
Section-aware chunker.

Splits text into retrieval-sized chunks that NEVER cross a CTD section
boundary (a limit in 3.2.S.4.1 must never be mistaken for one in 3.2.S.7).
Default size follows the M3 spec: ~512 tokens / 128 overlap, where "tokens"
here is a whitespace-word approximation — good enough for chunk sizing and
swappable later for a real tokenizer without changing the call shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP = 128


@dataclass
class SectionBlock:
    """One contiguous run of text already attributed to a single CTD section."""

    ctd_section: str
    text: str
    page: int | None = None
    confidence: float = 1.0


@dataclass
class TextChunk:
    text: str
    ctd_section: str
    page: int | None
    section_confidence: float
    chunk_index: int  # position within this section's blocks, 0-based


def _word_chunks(words: list[str], size: int, overlap: int) -> Iterable[list[str]]:
    if not words:
        return
    step = max(size - overlap, 1)
    i = 0
    n = len(words)
    while i < n:
        yield words[i : i + size]
        if i + size >= n:
            break
        i += step


def chunk_section_blocks(
    blocks: list[SectionBlock],
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[TextChunk]:
    """Chunk each SectionBlock independently; chunks never span two blocks."""
    chunks: list[TextChunk] = []
    for block in blocks:
        words = block.text.split()
        if not words:
            continue
        for idx, word_group in enumerate(_word_chunks(words, size, overlap)):
            chunks.append(
                TextChunk(
                    text=" ".join(word_group),
                    ctd_section=block.ctd_section,
                    page=block.page,
                    section_confidence=block.confidence,
                    chunk_index=idx,
                )
            )
    return chunks
