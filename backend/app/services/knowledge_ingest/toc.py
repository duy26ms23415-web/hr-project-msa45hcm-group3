"""Printed table of contents ("Mục lục"): detection, page-offset calibration, verification.

TOC pages are always excluded from section content so retrieval never returns
a contents line instead of the rule it points to.
"""
import re
from collections import Counter
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.services.knowledge_ingest.models import Line
from app.services.knowledge_ingest.text import compact, numbering_level

_TOC_TITLES = {"mucluc", "tableofcontents", "contents", "noidung"}
# "Điều 5. Nghỉ phép ........ 12" (leader dots/ellipsis/underscores)
_LEADER_RE = re.compile(r"^(?P<title>.*?\S)\s*(?:[.…·_]\s*){3,}\s*(?P<page>\d{1,3})\s*$")
# "Điều 5. Nghỉ phép    12" — only trusted on a page titled as a TOC.
_TRAILING_RE = re.compile(r"^(?P<title>.*\S)\s+(?P<page>\d{1,3})\s*$")
_MIN_VERIFIED_RATIO = 0.5
_SEARCH_WINDOW = 2


@dataclass
class TocEntry:
    title: str
    printed_page: int
    level: int
    page: int | None = None  # verified PDF page
    line_index: int | None = None


@dataclass
class TocResult:
    pages: set[int]
    entries: list[TocEntry]  # verified entries only; empty when the TOC is unusable


def _is_toc_title(line: Line) -> bool:
    return compact(line.text) in _TOC_TITLES


def _parse_entry(text: str, lenient: bool) -> tuple[str, int] | None:
    match = _LEADER_RE.match(text) or (_TRAILING_RE.match(text) if lenient else None)
    if not match:
        return None
    title = match.group("title").strip(" .…·_")
    if len(compact(title)) < 3:
        return None
    return title, int(match.group("page"))


def _toc_pages(pages: list[list[Line]]) -> set[int]:
    found: set[int] = set()
    for index, lines in enumerate(pages):
        if not lines:
            continue
        titled = any(_is_toc_title(line) for line in lines[:5])
        continued = index in found  # the previous page (1-based number == index) was TOC
        lenient = titled or continued
        parsed = sum(1 for line in lines if _parse_entry(line.text, lenient))
        leader = sum(1 for line in lines if _LEADER_RE.match(line.text))
        if (titled and parsed >= 2) or leader >= max(3, int(len(lines) * 0.4)) or (
                continued and parsed >= max(2, int(len(lines) * 0.5))):
            found.add(index + 1)
    return found


def _entries(pages: list[list[Line]], toc_pages: set[int]) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for number in sorted(toc_pages):
        lines = pages[number - 1]
        indents = sorted({round(line.x0) for line in lines})
        for line in lines:
            if _is_toc_title(line):
                continue
            parsed = _parse_entry(line.text, lenient=True)
            if not parsed:
                continue
            title, printed = parsed
            level = numbering_level(title)
            if level is None:
                # Unnumbered entries: indentation rank gives the hierarchy.
                level = min(indents.index(round(line.x0)) + 1, 6) if line.x0 and indents else 1
            entries.append(TocEntry(title=title[:300], printed_page=printed, level=level))
    return entries


def _line_matches(title: str, line: Line) -> bool:
    needle, text = compact(title), compact(line.text)
    if not needle or not text:
        return False
    if text.startswith(needle) or (needle.startswith(text) and len(text) >= 0.6 * len(needle)):
        return True
    return len(needle) >= 6 and fuzz.ratio(needle, text[:len(needle) + 10]) >= 88


def _find(title: str, pages: list[list[Line]], candidates, toc_pages: set[int]):
    for number in candidates:
        if number < 1 or number > len(pages) or number in toc_pages:
            continue
        for index, line in enumerate(pages[number - 1]):
            if _line_matches(title, line):
                return number, index
    return None


def detect_toc(pages: list[list[Line]]) -> TocResult:
    toc_pages = _toc_pages(pages)
    if not toc_pages:
        return TocResult(set(), [])
    entries = _entries(pages, toc_pages)
    if not entries:
        return TocResult(toc_pages, [])
    body = [number for number in range(1, len(pages) + 1) if number not in toc_pages]
    # Printed page numbers rarely equal PDF indexes (cover, roman front matter):
    # calibrate one document-wide offset from where headings actually appear.
    offsets = Counter()
    for entry in entries[:12]:
        hit = _find(entry.title, pages, body, toc_pages)
        if hit:
            offsets[hit[0] - entry.printed_page] += 1
    if not offsets:
        return TocResult(toc_pages, [])
    offset = offsets.most_common(1)[0][0]
    verified = []
    for entry in entries:
        expected = entry.printed_page + offset
        window = sorted(range(expected - _SEARCH_WINDOW, expected + _SEARCH_WINDOW + 1), key=lambda n: abs(n - expected))
        hit = _find(entry.title, pages, window, toc_pages)
        if hit:
            entry.page, entry.line_index = hit
            verified.append(entry)
    if len(verified) < max(2, len(entries) * _MIN_VERIFIED_RATIO):
        return TocResult(toc_pages, [])
    verified.sort(key=lambda entry: (entry.page, entry.line_index))
    return TocResult(toc_pages, verified)
