"""Sentence-aware chunks that stay verbatim slices of the section text.

Verbatim slices matter: grounded answers are validated by checking that the
model's evidence is a substring of the passage it cites.
"""
import re
from dataclasses import dataclass

from app.services.knowledge_ingest.text import compact

TARGET_CHARS = 900
OVERLAP_CHARS = 150
# Sentence/clause ends followed by whitespace, or line breaks. "1.5" never splits.
_BOUNDARY_RE = re.compile(r"(?<=[.!?;:])\s+|\n+")


@dataclass
class ChunkDraft:
    index: int
    content: str
    page_start: int | None
    page_end: int | None


def _units(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _BOUNDARY_RE.finditer(text):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    # Hard-split runs with no punctuation (tables, OCR) at whitespace.
    result = []
    for begin, end in spans:
        while end - begin > TARGET_CHARS * 1.5:
            cut = text.rfind(" ", begin, begin + TARGET_CHARS)
            cut = cut if cut > begin else begin + TARGET_CHARS
            result.append((begin, cut))
            begin = cut + 1 if text[cut:cut + 1] == " " else cut
        if end > begin:
            result.append((begin, end))
    return result


def split_text(text: str) -> list[str]:
    units = _units(text)
    if not units:
        return []
    chunks, first = [], 0
    while first < len(units):
        last = first
        while last + 1 < len(units) and units[last + 1][1] - units[first][0] <= TARGET_CHARS:
            last += 1
        chunks.append(text[units[first][0]:units[last][1]])
        if last + 1 >= len(units):
            break
        # Overlap: restart at the earliest unit within OVERLAP_CHARS of the end.
        next_first = last + 1
        while next_first - 1 > first and units[last][1] - units[next_first - 1][0] <= OVERLAP_CHARS:
            next_first -= 1
        first = next_first
    return chunks


def _page_of(fragment: str, page_texts: dict[int, str], default: int | None) -> int | None:
    probe = compact(fragment)[:40]
    if len(probe) >= 12:
        for number, text in page_texts.items():
            if probe in text:
                return number
    return default


def chunk_section(content: str, page_start: int | None, page_end: int | None,
                  pages_text: list[str] | None = None) -> list[ChunkDraft]:
    """Chunk one section; each chunk's pages are located inside the section range."""
    page_texts = {}
    if pages_text and page_start and page_end and page_end > page_start:
        page_texts = {number: compact(pages_text[number - 1])
                      for number in range(page_start, min(page_end, len(pages_text)) + 1)}
    result = []
    for index, chunk in enumerate(split_text(content)):
        first = _page_of(chunk[:120], page_texts, page_start)
        last = _page_of(chunk[-120:], page_texts, page_end)
        if first and last and last < first:
            last = first
        result.append(ChunkDraft(index, chunk, first, last))
    return result
