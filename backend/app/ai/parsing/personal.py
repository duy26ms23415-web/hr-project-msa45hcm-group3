"""Rule-path detection of the actor's own records (input is canonical, unaccented text)."""
import re
from datetime import date, timedelta

# A first-person subject or an explicit period makes the question about the actor's
# own records; "đi muộn bị phạt thế nào?" stays a policy question.
_PERIOD = re.compile(r"\b(?:hom nay|hom qua|tuan nay|tuan truoc|thang nay|thang truoc)\b|\bngay \d{1,2}\b")
_PERSONAL = re.compile(r"\b(?:toi|minh|t|em)\b|" + _PERIOD.pattern)
# "Nhân viên của tôi", "nhóm tôi": a team question, never the actor's own records.
_TEAM = re.compile(r"\b(?:nhan vien|nhom|team|phong ban|cong ty|moi nguoi|ai)\b")


def _personal(text: str) -> bool:
    return bool(_PERSONAL.search(text)) and not _TEAM.search(text)


def is_team_records_query(text: str) -> bool:
    return (bool(_TEAM.search(text)) and bool(re.search(r"\b(?:cong|cham cong|phep|nghi|di muon|di tre)\b", text))
            and not any(term in text for term in ("quy dinh", "chinh sach", "noi quy")))

_ATTENDANCE_TERMS = (
    "ngay thieu", "thieu cong", "bao nhieu cong", "ngay cong", "du cong", "cong cua toi", "ngay nao quen",
    "ngay nao thieu", "tinh trang cham cong", "cham cong cua toi", "cham cong ban than", "cham cong chua",
    "di muon", "di tre", "ve som", "check-in luc", "check in luc", "check-out luc", "check out luc",
    "cham cong luc", "gio vao", "gio ra", "may gio vao", "may gio ra",
)
_LATENESS_TERMS = ("di muon", "di tre", "ve som")


def is_attendance_query(text: str) -> bool:
    # "Tuần trước tôi chấm công thế nào": a period makes plain "chấm công" a records question.
    return _personal(text) and (any(term in text for term in _ATTENDANCE_TERMS)
                                or "cham cong" in text and bool(_PERIOD.search(text)))


def asks_question(message: str, text: str) -> bool:
    """A question, not a statement ("hôm qua tôi quên chấm công" answers an open fix form).

    "chưa"/"không" ask only at the end; mid-sentence they negate ("tôi chưa chấm công ra")."""
    return "?" in message or bool(re.search(
        r"\b(?:may (?:gio|lan|ngay|buoi|cong|phut)|bao nhieu|luc nao|ngay nao|the nao|ra sao)\b"
        r"|\b(?:chua|khong)\s*$", text))


def asks_lateness(text: str) -> bool:
    return any(term in text for term in _LATENESS_TERMS)


def is_leave_status_query(text: str) -> bool:
    """"Đơn của tôi duyệt chưa?" — the actor's own requests, not a manager's queue."""
    # Whole word: "don" is also inside "dong" (đóng, hợp đồng, lao động). A report request is not a lookup.
    return (bool(re.search(r"\bdon\b", text)) and "cho toi duyet" not in text and _personal(text)
            and not re.search(r"\b(?:bao cao|xuat|thong ke)\b", text)
            and bool(re.search(r"\b(?:duyet chua|da duoc duyet|trang thai|tinh trang|bi tu choi|da gui)\b", text)))


_FIRST_PERSON = re.compile(r"\b(?:toi|minh|em|tui)\b")


def is_rule_question(text: str) -> bool:
    """A question about what the company grants or when, not about anyone's records.

    "Công ty cho nghỉ phép bao nhiêu ngày?", "Nhân viên được nghỉ mấy ngày mỗi năm?",
    "Lương tháng này khi nào trả?" are answered from the policy documents."""
    if re.search(r"\b(?:bao cao|thong ke|xuat|bieu do|phieu luong)\b", text):
        return False  # Report wording keeps the report flow.
    when = r"\b(?:khi nao|bao gio|ngay nao|luc nao|hom nao|ngay may)\b"
    if re.search(r"\b(?:luong|thuong)\b", text) and re.search(when, text) and re.search(
            r"\b(?:tra|nhan|chi|phat|chuyen|ve)\b", text):
        return True
    # Records, not rules: the speaker's own, a group's, a dated period ("hôm qua được tính công chưa?"
    # drops the pronoun), or what is left of a balance ("còn" — but "con ốm" is a child).
    if (_FIRST_PERSON.search(text) or _PERIOD.search(text)
            or re.search(r"\b(?:nhom|team|phong|bo phan)\b", text)
            or re.search(r"\bcon (?:lai|bao nhieu|may|duoc|ngay|phep|nghi)\b", text)):
        return False
    grant = r"(?:nghi|phep|huong|duoc|lam|tang|tinh)"
    return bool(re.search(rf"\bcong ty (?:cho|quy dinh|ap dung)\b.{{0,15}}\b{grant}\b"
                          r"|\bduoc (?:nghi|huong|cong|tinh|phep|tang)\b"
                          r"|\b(?:moi|mot|hang) (?:nam|thang)\b.{0,30}\b(?:bao nhieu|may) ngay\b"
                          r"|\b(?:bao nhieu|may) ngay\b.{0,30}\b(?:moi|mot|hang) (?:nam|thang)\b", text))


def is_own_salary_query(text: str) -> bool:
    return (bool(re.search(r"\bluong\b", text)) and _personal(text)
            and not any(term in text for term in ("phieu luong", "bao cao", "cach tinh", "chinh sach", "quy dinh", "thue")))


def is_remote_request(text: str) -> bool:
    """A remote-work booking ("tôi muốn làm remote thứ hai"), not "remote có được không?"."""
    return (bool(re.search(r"\b(?:remote|wfh|tu xa)\b", text))
            and bool(re.search(r"\b(?:muon|can|dang ky|xin|cho toi)\b", text)))


def week_period(text: str, today: date) -> tuple[date, date] | None:
    """Monday-based week; the current week stops at today."""
    monday = today - timedelta(days=today.weekday())
    if "tuan truoc" in text:
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if "tuan nay" in text:
        return monday, today
    return None
