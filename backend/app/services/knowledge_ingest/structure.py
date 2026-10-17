"""Derive a section tree from any PDF without document-specific configuration.

Priority: PDF bookmarks → printed table of contents → layout (font size,
weight, numbering). Each section's content runs from its heading to the next
heading, across pages, so no text is duplicated between sections.
"""
import logging
import re
import statistics
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.services.knowledge_ingest.models import Line, SectionDraft, StructureResult
from app.services.knowledge_ingest.text import compact, decimal_number, numbering_level
from app.services.knowledge_ingest.toc import _line_matches, detect_toc
from app.services.knowledge_retrieval import normalize

logger = logging.getLogger(__name__)

MAX_SECTIONS = 200
_MAX_HEADING_CHARS = 160
_MIN_PREAMBLE_CHARS = 40
_LETTER_ITEM_RE = re.compile(r"^\s*[a-z][.)]\s")


@dataclass
class Anchor:
    page: int
    line_index: int
    heading: str
    level: int
    title: str = ""  # Bookmark title; names a parent that shares its line with a child in the heading path.


def _outline_entries(raw: bytes) -> list[tuple[str, int, int]]:
    """(title, 1-based page, depth) for every bookmark that resolves to a page."""
    try:
        reader = PdfReader(BytesIO(raw), strict=False)
        result: list[tuple[str, int, int]] = []

        def walk(items, depth):
            for item in items:
                if isinstance(item, list):
                    walk(item, depth + 1)
                    continue
                try:
                    page = reader.get_destination_page_number(item)
                except Exception:
                    continue
                title = " ".join(str(getattr(item, "title", "") or "").split())
                if title and page is not None and page >= 0:
                    result.append((title[:300], page + 1, depth))

        walk(reader.outline, 1)
        return result
    except Exception:
        logger.info("knowledge_outline_unreadable", exc_info=True)
        return []


def _locate(title: str, pages: list[list[Line]], page: int, skip: set[int]) -> tuple[int, int] | None:
    for number in (page, page + 1, page - 1):
        if 1 <= number <= len(pages) and number not in skip:
            for index, line in enumerate(pages[number - 1]):
                if _line_matches(title, line):
                    return number, index
    return None


def _outline_anchors(raw: bytes, pages: list[list[Line]], skip: set[int]) -> list[Anchor]:
    entries = _outline_entries(raw)
    anchors = []
    for title, page, depth in entries:
        hit = _locate(title, pages, page, skip)
        if hit:
            line = pages[hit[0] - 1][hit[1]]
            anchors.append(Anchor(hit[0], hit[1], line.text[:300], min(depth, 6), title.strip()[:300]))
    # Bookmarks that do not point at visible headings are not trustworthy structure.
    if not entries or len(anchors) < max(2, len(entries) * 0.5):
        return []
    return anchors


def _body_size(pages: list[list[Line]]) -> float | None:
    weighted = [line.size for lines in pages for line in lines for _ in range(min(len(line.text), 200)) if line.size]
    return statistics.median(weighted) if weighted else None


def _looks_like_heading(line: Line, body_size: float | None) -> int | None:
    """Heading level from typography/numbering, or None for body text."""
    text = line.text.strip()
    letters = sum(char.isalpha() for char in text)
    if not text or letters < 3 or len(text) > _MAX_HEADING_CHARS:
        return None
    numbered = numbering_level(text)
    larger = bool(body_size and line.size and line.size >= body_size * 1.15)
    sentence_like = text.endswith((",", ";")) or (text.endswith(".") and len(text) > 80)
    if sentence_like:
        return None
    upper = letters >= 6 and text.upper() == text
    if numbered is not None:
        # Lettered list items ("a) ...") are only headings when emphasized.
        if _LETTER_ITEM_RE.match(normalize(text)) and not (line.bold or larger):
            return None
        return numbered
    if larger:
        return 1 if body_size and line.size >= body_size * 1.4 else 2
    if (line.bold or upper) and len(text) <= 100:
        return 2
    return None


def _layout_anchors(pages: list[list[Line]], skip: set[int]) -> list[Anchor]:
    body_size = _body_size(pages)
    anchors = []
    for number, lines in enumerate(pages, 1):
        if number in skip:
            continue
        for index, line in enumerate(lines):
            level = _looks_like_heading(line, body_size)
            if level is not None:
                anchors.append(Anchor(number, index, line.text[:300], level))
    return anchors


def _merge_numbered_children(anchors: list[Anchor], pages, skip) -> list[Anchor]:
    """Bookmarks/TOC usually list top levels only; keep deeper numbered headings too."""
    taken = {(anchor.page, anchor.line_index) for anchor in anchors}
    extra = [anchor for anchor in _layout_anchors(pages, skip)
             if (anchor.page, anchor.line_index) not in taken and numbering_level(anchor.heading) is not None]
    merged = sorted(anchors + extra, key=lambda anchor: (anchor.page, anchor.line_index))
    trusted = set(map(id, anchors))
    kept, parent = [], None
    for anchor in merged:
        if id(anchor) in trusted:
            parent = anchor
            kept.append(anchor)
            continue
        number, parent_number = decimal_number(anchor.heading), decimal_number(parent.heading) if parent else None
        if parent_number:
            if not number or not number.startswith(parent_number + "."):
                continue  # e.g. "1. Mở bảng công" under "4.2" is a list step, not a section
        elif number and "." in number:
            continue  # "1.2" under an unnumbered/named parent cannot be verified
        anchor.level = min((parent.level if parent else 0) + 1, 6)
        kept.append(anchor)
    return kept


def _build(anchors: list[Anchor], pages: list[list[Line]], skip: set[int]) -> list[SectionDraft]:
    # On a shared line the parent comes first, so the child keeps the text and the parent stays in its path.
    anchors = sorted(anchors, key=lambda anchor: (anchor.page, anchor.line_index, anchor.level))
    positions = [(number, index) for number, lines in enumerate(pages, 1) if number not in skip
                 for index in range(len(lines))]
    order = {position: rank for rank, position in enumerate(positions)}
    starts = [order[(anchor.page, anchor.line_index)] for anchor in anchors]
    drafts: list[SectionDraft] = []
    if starts and starts[0] > 0:
        preamble = [pages[n - 1][i] for n, i in positions[:starts[0]]]
        text = "\n".join(line.text for line in preamble)
        if len(compact(text)) >= _MIN_PREAMBLE_CHARS:
            drafts.append(SectionDraft("", preamble[0].text[:300], preamble[0].page, preamble[-1].page, text, level=1))
    stack: list[tuple[int, str]] = []
    for position, anchor in enumerate(anchors):
        end = starts[position + 1] if position + 1 < len(anchors) else len(positions)
        lines = [pages[n - 1][i] for n, i in positions[starts[position]:end]]
        while stack and stack[-1][0] >= anchor.level:
            stack.pop()
        if not lines:
            # Shares its line with the next anchor (bookmark "Phụ lục" and its child "Phụ lục 1"):
            # no own text, but it stays in the heading path under its own name, not the child's line.
            stack.append((anchor.level, anchor.title or anchor.heading))
            continue
        stack.append((anchor.level, anchor.heading))
        drafts.append(SectionDraft(
            "", anchor.heading, lines[0].page, lines[-1].page, "\n".join(line.text for line in lines),
            level=anchor.level, heading_path=" > ".join(heading for _, heading in stack),
        ))
    return drafts


def _limit(anchors: list[Anchor]) -> list[Anchor]:
    """Coarsen to at most MAX_SECTIONS by dropping the deepest levels first."""
    while len(anchors) > MAX_SECTIONS - 1:
        deepest = max(anchor.level for anchor in anchors)
        if deepest <= 1:
            return anchors[:MAX_SECTIONS - 1]
        anchors = [anchor for anchor in anchors if anchor.level < deepest]
    return anchors


def page_sections(pages: list[list[Line]], skip: set[int] = frozenset()) -> list[SectionDraft]:
    """Last resort: one section per non-empty page."""
    return [SectionDraft("", lines[0].text[:300], number, number, "\n".join(line.text for line in lines))
            for number, lines in enumerate(pages, 1) if lines and number not in skip]


def _finalize(drafts: list[SectionDraft]) -> list[SectionDraft]:
    for index, draft in enumerate(drafts, 1):
        draft.section_code = f"S{index:03d}"
        draft.heading = draft.heading.strip()[:300]
        draft.heading_path = (draft.heading_path or draft.heading)[:2000]
    return drafts


def build_structure(raw: bytes, pages: list[list[Line]]) -> StructureResult:
    toc = detect_toc(pages)
    skip = toc.pages
    method = "OUTLINE"
    anchors = _outline_anchors(raw, pages, skip)
    if not anchors and toc.entries:
        method = "PRINTED_TOC"
        anchors = [Anchor(entry.page, entry.line_index, pages[entry.page - 1][entry.line_index].text[:300], entry.level)
                   for entry in toc.entries]
    if anchors:
        anchors = _merge_numbered_children(anchors, pages, skip)
    else:
        method = "LAYOUT"
        anchors = _layout_anchors(pages, skip)
    anchors = _limit(anchors)
    drafts = _build(anchors, pages, skip) if anchors else []
    if not anchors or not drafts:
        return StructureResult(_finalize(page_sections(pages, skip)), "PAGE", skip)
    return StructureResult(_finalize(drafts), method, skip)
