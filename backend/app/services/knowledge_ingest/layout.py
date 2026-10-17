"""Line-level PDF layout (font size, weight, position) with running headers removed."""
import logging
import re
import statistics
from collections import Counter
from io import BytesIO

import pdfplumber

from app.services.knowledge_ingest.models import Line
from app.services.knowledge_ingest.text import compact
from app.services.knowledge_storage import clean_extracted_text

logger = logging.getLogger(__name__)

_MARGIN_RATIO = 0.08
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:trang|page)?\s*[-–]?\s*\d{1,3}\s*(?:/\s*\d{1,3}|[-–])?\s*$", re.IGNORECASE)
_BOLD_RE = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)


def _plumber_lines(raw: bytes) -> list[list[Line]]:
    pages: list[list[Line]] = []
    with pdfplumber.open(BytesIO(raw)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            lines = []
            for item in page.extract_text_lines(return_chars=True, strip=True):
                text = " ".join(clean_extracted_text(item["text"]).split())
                if not text:
                    continue
                chars = [char for char in item.get("chars", []) if char.get("text", "").strip()]
                sizes = [round(float(char["size"]), 1) for char in chars if char.get("size")]
                bold_chars = sum(1 for char in chars if _BOLD_RE.search(char.get("fontname", "")))
                lines.append(Line(
                    page=number, text=text, size=statistics.median(sizes) if sizes else None,
                    bold=bool(chars) and bold_chars / len(chars) >= 0.6,
                    top=float(item.get("top", 0)), x0=float(item.get("x0", 0)), page_height=float(page.height or 0),
                ))
            pages.append(lines)
    return pages


def _plain_lines(pages_text: list[str]) -> list[list[Line]]:
    return [[Line(page=number, text=" ".join(line.split()), top=float(index))
             for index, line in enumerate(text.splitlines()) if line.strip()]
            for number, text in enumerate(pages_text, 1)]


def _strip_running_text(pages: list[list[Line]]) -> list[list[Line]]:
    """Drop page numbers and headers/footers repeated in page margins."""
    if not pages:
        return pages
    def in_margin(line: Line, lines: list[Line]) -> bool:
        if line.page_height:
            return line.top < line.page_height * _MARGIN_RATIO or line.top > line.page_height * (1 - _MARGIN_RATIO)
        return line is lines[0] or line is lines[-1]

    def signature(line: Line) -> str:
        return re.sub(r"\d+", "#", compact(line.text))

    repeated = Counter()
    for lines in pages:
        repeated.update({signature(line) for line in lines if in_margin(line, lines)})
    threshold = max(3, (len(pages) + 1) // 2)
    running = {key for key, count in repeated.items() if key and count >= threshold}
    cleaned = []
    for lines in pages:
        cleaned.append([line for line in lines if not (in_margin(line, lines) and (
            signature(line) in running or _PAGE_NUMBER_RE.match(line.text)))])
    return cleaned


def extract_lines(raw: bytes, pages_text: list[str]) -> list[list[Line]]:
    """Per-page lines; falls back to plain text lines when layout parsing fails."""
    try:
        pages = _plumber_lines(raw)
        if len(pages) != len(pages_text):
            raise ValueError("page count mismatch")
    except Exception:  # pdfminer raises many exception types on unusual PDFs
        logger.info("knowledge_layout_fallback", exc_info=True)
        pages = _plain_lines(pages_text)
    return _strip_running_text(pages)
