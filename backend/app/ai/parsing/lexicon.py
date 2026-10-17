"""Canonical text for keyword routing: accents, teencode, spacing and small typos.

Only the rule-based path depends on this (Gemini disabled, drafts, report
runs). It rewrites a copy used for matching; the user's message is unchanged.
"""
import re
from functools import lru_cache

from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from app.services.knowledge_retrieval import normalize

# Whole-token abbreviations common in Vietnamese chat.
_TOKENS = {
    # Single letters ("a", "e", "t") are left alone: they are also names and codes.
    # Not "hong" (also "hồng") or "tk" (usually "tài khoản").
    "ko": "khong", "k": "khong", "kh": "khong", "hok": "khong", "hem": "khong", "kg": "khong",
    "dc": "duoc", "đc": "duoc", "dk": "duoc", "j": "gi", "ntn": "nhu the nao",
    "bn": "bao nhieu", "bnh": "bao nhieu", "bnhieu": "bao nhieu", "mk": "minh", "mik": "minh", "mjk": "minh",
    "tui": "toi", "tớ": "toi",
    "cty": "cong ty", "nv": "nhan vien", "ql": "quan ly", "sep": "quan ly", "bc": "bao cao",
    "hnay": "hom nay", "hqua": "hom qua", "hum": "hom", "trc": "truoc", "ng": "nguoi", "vs": "voi",
    "fep": "phep", "ngi": "nghi", "ngỉ": "nghi", "xinh": "xin", "lm": "lam", "vc": "viec",
    "ccong": "cham cong", "cc": "cham cong", "gtrinh": "giai trinh", "lg": "luong",
    "off": "nghi", "dayoff": "nghi phep",
}
# Phrases rewritten after token expansion (canonical forms used by routing keywords).
_PHRASES = [
    (r"\bcheck\s*-?\s*in\b|\bchek\s*in\b|\bcheckin\b", "check-in"),
    (r"\bcheck\s*-?\s*out\b|\bchek\s*out\b|\bcheckout\b", "check-out"),
    (r"\bquen\s+(?:bam\s+(?:the|cong)|quet\s+the)\b", "quen quet"),
    (r"\blam\s+(?:o|tai)\s+nha\b|\blam\s+online\b|\bwork\s+from\s+home\b", "lam viec tu xa"),
    (r"\bngay\s+phep\s+con\b", "phep con lai"),
    (r"\bmay\s+(?:hom|bua)\b", "may ngay"),
]
# Domain words: merged-word splitting uses all of them, typo snapping only the long ones.
_VOCAB = sorted(set(
    "nghi phep cham cong bao cao xin don giai trinh duyet quen quet luong chinh sach quy dinh thang tuan "
    "nhieu remote check thong tong hop nhan vien phong ban hom nay ngay mai truoc tuan sau lich su "
    "huong dan thu tuc dieu kien noi quy kiem tra xem tinh trang so du con lai tang ca".split()
))
_LONG_VOCAB = [word for word in _VOCAB if len(word) >= 5]
_KEEP = set(_TOKENS.values()) | set(_VOCAB)


# A well-formed Vietnamese syllable (onset + vowels + coda) is a real word or a
# name ("thanh", "phuong"), never a typo to snap onto the domain vocabulary.
_SYLLABLE = re.compile(
    r"(?:ngh|ng|nh|ch|gh|gi|kh|ph|qu|th|tr|[bcdghklmnprstvx])?[aeiouy]{1,3}(?:ng|nh|ch|[cmnpt])?"
)
_EDGE_RE = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


@lru_cache(maxsize=4096)
def _correct(token: str) -> str:
    if len(token) < 5 or not token.isalpha() or token in _KEEP or _SYLLABLE.fullmatch(token):
        return token
    # Merged words: "xinnghi" -> "xin nghi", "chamcong" -> "cham cong".
    for cut in range(2, len(token) - 1):
        if token[:cut] in _KEEP and token[cut:] in _KEEP:
            return f"{token[:cut]} {token[cut:]}"
    # Short syllables are too close to each other (than/thang, long/luong) to correct.
    # One edit or swapped letters ("thnag" -> "thang").
    match = process.extractOne(token, _LONG_VOCAB, scorer=DamerauLevenshtein.normalized_similarity, score_cutoff=0.79)
    # Same first letter keeps names and unrelated words from being "corrected".
    return match[0] if match and match[0][0] == token[0] else token


def _map_tokens(text: str, mapper) -> str:
    """Rewrite word cores only, so "17:30", "10/10/2026" and "EMP003," stay intact."""
    result = []
    for token in text.split():
        lead, core, tail = _EDGE_RE.match(token).groups()
        result.append(lead + mapper(core) + tail)
    return " ".join(result)


def canonical(text: str) -> str:
    """normalize() plus abbreviation expansion, phrase canonicalization and typo snapping."""
    # Map accented abbreviations ("tớ", "ngỉ") before accents are stripped.
    value = normalize(_map_tokens(text.lower(), lambda core: _TOKENS.get(core, core)))
    # Second pass catches accented teencode ("fép"); _TOKENS has no key that is
    # also a common accent-stripped word.
    value = _map_tokens(value, lambda core: _TOKENS.get(core) or _correct(core))
    for pattern, replacement in _PHRASES:
        value = re.sub(pattern, replacement, value)
    return re.sub(r"\s+", " ", value).strip()
