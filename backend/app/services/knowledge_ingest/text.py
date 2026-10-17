"""Text comparison helpers tolerant to PDF extraction differences."""
import re
import unicodedata

from rapidfuzz import fuzz

from app.services.knowledge_retrieval import normalize

# Structural numbering used by Vietnamese and English policy documents.
NUMBERING_RE = re.compile(
    r"^\s*(?:"
    r"(?P<named>(?:chuong|phan|muc|dieu|chapter|section|part|article)\s+(?:[0-9]+|[ivxlc]+)\b)"
    r"|(?P<roman>[ivxlc]{1,6}[.)])\s"
    # "1." / "1)" / "1.2" / "1.2.3." — a bare "3 ngay" is body text, not numbering.
    r"|(?P<decimal>\d{1,3}(?:\.\d{1,3}){1,4}\.?|\d{1,3}[.)])\s"
    r"|(?P<letter>[a-zđ][.)])\s"
    r")",
)


def compact(text: str) -> str:
    """Accent-free alphanumerics only, so spacing/diacritic extraction noise is ignored."""
    return re.sub(r"[^a-z0-9]", "", normalize(unicodedata.normalize("NFC", text or "")))


def heading_matches(heading: str, text: str, threshold: int = 90) -> bool:
    """True when the heading occurs in the text, allowing small extraction drift."""
    needle, haystack = compact(heading), compact(text)
    if not needle or not haystack:
        return False
    if needle in haystack:
        return True
    return len(needle) >= 8 and fuzz.partial_ratio(needle, haystack) >= threshold


def decimal_number(text: str) -> str | None:
    """'4.2.1' for '4.2.1. Tiêu đề', else None."""
    match = NUMBERING_RE.match(normalize(text))
    return match.group("decimal").rstrip(".)") if match and match.group("decimal") else None


def numbering_level(text: str) -> int | None:
    """Heading depth implied by its numbering, or None when unnumbered."""
    match = NUMBERING_RE.match(normalize(text))
    if not match:
        return None
    if match.group("named"):
        word = match.group("named").split()[0]
        return 1 if word in {"chuong", "phan", "chapter", "part"} else 2
    if match.group("roman"):
        return 1
    if match.group("decimal"):
        return min(match.group("decimal").rstrip(".)").count(".") + 1, 6)
    return 3
