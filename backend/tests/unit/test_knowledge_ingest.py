"""Dynamic PDF structure: bookmarks, printed TOC (Mục lục), fonts, Gemini fallback."""
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.knowledge_ingest import gemini_fallback, pipeline
from app.services.knowledge_ingest.chunker import chunk_section, split_text
from app.services.knowledge_ingest.gemini_fallback import _Section, _Structure
from app.services.knowledge_ingest.text import heading_matches, numbering_level
from app.services.knowledge_storage import parse_pdf

W, H = A4
BODY = [
    [("Chuong I. Quy dinh chung", 15), ("Dieu 1. Pham vi ap dung", 12),
     ("Noi quy nay ap dung cho toan bo nhan vien chinh thuc va thu viec.", 0),
     ("Dieu 2. Gio lam viec", 12), ("Gio lam viec tu 08:00 den 17:00, nghi trua tu 12:00 den 13:00.", 0)],
    [("Chuong II. Nghi phep", 15), ("Dieu 3. Nghi phep nam", 12),
     ("Nhan vien duoc nghi 12 ngay phep nam. Nghi phep phai bao truoc it nhat 3 ngay lam viec.", 0)],
    [("Khong duoc nghi phep qua 5 ngay lien tuc neu chua duoc quan ly dong y.", 0),
     ("Dieu 4. Lam viec tu xa", 12), ("Nhan vien duoc lam viec tu xa toi da 2 ngay moi tuan.", 0)],
]
TOC = [("Chuong I. Quy dinh chung", 1), ("Dieu 1. Pham vi ap dung", 1), ("Dieu 2. Gio lam viec", 1),
       ("Chuong II. Nghi phep", 2), ("Dieu 3. Nghi phep nam", 2), ("Dieu 4. Lam viec tu xa", 3)]


def make_pdf(*, toc=None, front_pages=1, bookmarks=False, body=BODY) -> bytes:
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    for _ in range(front_pages):
        c.setFont("Helvetica-Bold", 22)
        c.drawString(80, H / 2, "NOI QUY LAO DONG")
        c.showPage()
    if toc:
        for page_entries in toc:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(60, H - 80, "MUC LUC")
            c.setFont("Helvetica", 11)
            y = H - 120
            for title, printed in page_entries:
                c.drawString(60, y, f"{title} {'.' * 40} {printed}")
                y -= 18
            c.showPage()
    for number, lines in enumerate(body, 1):
        # Running header/footer repeated on every body page.
        c.setFont("Helvetica", 8)
        c.drawString(40, H - 25, "CONG TY ABC - Noi quy lao dong")
        c.drawString(W / 2, 20, f"Trang {number}")
        y = H - 80
        for text, size in lines:
            c.setFont("Helvetica-Bold" if size else "Helvetica", size or 10)
            c.drawString(60, y, text)
            if bookmarks and size == 15:
                key = f"b{number}{y}"
                c.bookmarkPage(key, top=y)
                c.addOutlineEntry(text, key, level=0)
            y -= 22
        c.showPage()
    c.save()
    return output.getvalue()


async def build(raw):
    return await pipeline.build_sections(raw, parse_pdf(raw).pages)


def by_heading(result):
    return {section.heading: section for section in result.sections}


@pytest.mark.asyncio
async def test_printed_toc_maps_printed_pages_to_pdf_pages_and_is_excluded():
    raw = make_pdf(toc=[TOC], front_pages=1)
    result = await build(raw)
    assert result.method == "PRINTED_TOC"
    assert result.toc_pages == {2}
    sections = by_heading(result)
    # Printed page 1 is PDF page 3 (cover + TOC before the body).
    assert sections["Dieu 1. Pham vi ap dung"].page_start == 3
    assert sections["Dieu 4. Lam viec tu xa"].page_start == 5
    assert sections["Dieu 3. Nghi phep nam"].heading_path == "Chuong II. Nghi phep > Dieu 3. Nghi phep nam"
    assert all("...." not in section.content and "MUC LUC" not in section.content for section in result.sections)


@pytest.mark.asyncio
async def test_multi_page_toc_with_offset_from_extra_front_matter():
    raw = make_pdf(toc=[TOC[:3], TOC[3:]], front_pages=2)
    result = await build(raw)
    assert result.method == "PRINTED_TOC" and result.toc_pages == {3, 4}
    assert by_heading(result)["Dieu 3. Nghi phep nam"].page_start == 6


@pytest.mark.asyncio
async def test_toc_entries_that_do_not_exist_are_dropped_and_garbage_toc_falls_back():
    wrong = [*TOC, ("Dieu 9. Muc khong ton tai", 3)]
    result = await build(make_pdf(toc=[wrong]))
    assert result.method == "PRINTED_TOC"
    assert "Dieu 9. Muc khong ton tai" not in by_heading(result)
    garbage = [(f"Muc rac so {index}", 40 + index) for index in range(6)]
    fallback = await build(make_pdf(toc=[garbage]))
    assert fallback.method == "LAYOUT"
    assert fallback.toc_pages == {2}  # still excluded from content


@pytest.mark.asyncio
async def test_bookmarks_win_over_printed_toc():
    result = await build(make_pdf(toc=[TOC], bookmarks=True))
    assert result.method == "OUTLINE"
    # Numbered articles below the bookmarked chapters are kept as children.
    assert by_heading(result)["Dieu 3. Nghi phep nam"].heading_path == "Chuong II. Nghi phep > Dieu 3. Nghi phep nam"


@pytest.mark.asyncio
async def test_layout_sections_cross_pages_without_duplicate_text_or_running_headers():
    result = await build(make_pdf())
    assert result.method == "LAYOUT"
    article = by_heading(result)["Dieu 3. Nghi phep nam"]
    assert (article.page_start, article.page_end) == (3, 4)
    assert "Khong duoc nghi phep qua 5 ngay" in article.content
    assert "Lam viec tu xa" not in article.content
    contents = [section.content for section in result.sections]
    assert all("CONG TY ABC" not in text and "Trang " not in text for text in contents)
    assert sum("12 ngay phep nam" in text for text in contents) == 1


@pytest.mark.asyncio
async def test_unstructured_pdf_uses_gemini_headings_but_keeps_pdf_text(monkeypatch):
    body = [[("mot so quy dinh ve nghi phep cua cong ty", 0), ("nhan vien duoc nghi 12 ngay moi nam.", 0),
             ("quy dinh ve lam viec tu xa", 0), ("toi da 2 ngay moi tuan.", 0)]]
    raw = make_pdf(body=body, front_pages=0)
    monkeypatch.setattr(gemini_fallback, "pdf_structure_ready", lambda: True)
    ask = AsyncMock(return_value=_Structure(sections=[
        _Section(heading="mot so quy dinh ve nghi phep cua cong ty", level=1, page_start=1, page_end=1),
        _Section(heading="quy dinh ve lam viec tu xa", level=1, page_start=1, page_end=1),
        _Section(heading="Muc do model tu bia", level=1, page_start=1, page_end=1),
    ]))
    monkeypatch.setattr(gemini_fallback, "_ask", ask)
    result = await build(raw)
    assert result.method == "GEMINI_STRUCTURE"
    assert [section.heading for section in result.sections] == [
        "mot so quy dinh ve nghi phep cua cong ty", "quy dinh ve lam viec tu xa"]
    assert result.sections[1].content == "quy dinh ve lam viec tu xa\ntoi da 2 ngay moi tuan."
    assert ask.await_args.kwargs["transcribe"] is False


@pytest.mark.asyncio
async def test_scanned_pdf_uses_gemini_transcription_and_validates_pages(monkeypatch):
    output = BytesIO()
    c = canvas.Canvas(output)
    c.rect(50, 50, 100, 100)  # no text layer
    c.showPage()
    c.save()
    raw = output.getvalue()
    monkeypatch.setattr(gemini_fallback, "pdf_structure_ready", lambda: True)
    monkeypatch.setattr(gemini_fallback, "_ask", AsyncMock(return_value=_Structure(sections=[
        _Section(heading="Điều 1. Nghỉ phép", level=1, page_start=1, page_end=1, text="Điều 1. Nghỉ phép\nĐược nghỉ 12 ngày."),
        _Section(heading="Điều 2. Sai trang", level=1, page_start=5, page_end=6, text="Điều 2. Sai trang"),
    ])))
    result = await pipeline.build_sections(raw, parse_pdf(raw, allow_textless=True).pages)
    assert result.method == "GEMINI_OCR"
    assert [section.heading for section in result.sections] == ["Điều 1. Nghỉ phép"]


@pytest.mark.asyncio
async def test_scanned_pdf_without_gemini_is_rejected():
    from app.services.knowledge_storage import PDFValidationError
    with pytest.raises(PDFValidationError) as error:
        await pipeline.build_sections(b"%PDF-1.4", [""])
    assert error.value.code == "PDF_TEXT_REQUIRED"


def test_manifest_sections_cut_at_next_heading_and_reject_missing_heading():
    from app.schemas.knowledge import KnowledgeSectionInput
    from app.services.knowledge_storage import PDFValidationError
    raw = make_pdf()
    pages = parse_pdf(raw).pages
    manifest = [
        KnowledgeSectionInput(section_code="A", heading="Dieu 3. Nghi phep nam", page_start=3, page_end=4),
        KnowledgeSectionInput(section_code="B", heading="Dieu 4. Lam viec tu xa", page_start=4, page_end=4, is_answerable=False),
    ]
    drafts = pipeline.sections_from_manifest(raw, pages, manifest)
    assert [draft.section_code for draft in drafts] == ["A", "B"]
    assert "Khong duoc nghi phep" in drafts[0].content and "tu xa" not in drafts[0].content
    assert drafts[1].is_answerable is False
    with pytest.raises(PDFValidationError) as error:
        pipeline.sections_from_manifest(raw, pages, [KnowledgeSectionInput(
            section_code="X", heading="Heading that is not printed", page_start=2, page_end=2)])
    assert error.value.code == "PDF_SECTION_HEADING_MISMATCH"


def test_heading_matching_tolerates_extraction_spacing_and_accents():
    assert heading_matches("Điều 5. Nghỉ phép", "...\nDieu  5 .Nghi phep\nNoi dung")
    assert not heading_matches("Điều 9. Không có", "Điều 5. Nghỉ phép")
    assert numbering_level("1.2.3 Quy trình") == 3
    assert numbering_level("Chương II Nghỉ phép") == 1
    assert numbering_level("3 ngày làm việc") is None


def test_chunks_are_verbatim_slices_with_overlap_and_unbroken_numbers():
    sentence = "Nhân viên được nghỉ 1.5 ngày khi làm thêm giờ vào ngày lễ theo quy định. "
    text = sentence * 40
    chunks = split_text(text)
    assert len(chunks) > 2
    assert all(chunk in text for chunk in chunks)
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert all("1.5" in chunk or "1." not in chunk[-3:] for chunk in chunks)
    # Consecutive chunks overlap so a sentence on the boundary is never lost.
    assert chunks[1][:40] in chunks[0]


def test_chunk_pages_are_located_inside_multi_page_sections():
    pages = ["Dieu 3. Nghi phep nam\n" + "Nhan vien duoc nghi phep nam. " * 40,
             "Khong duoc nghi qua 5 ngay lien tuc. " * 40]
    content = pages[0] + "\n" + pages[1]
    chunks = chunk_section(content, 1, 2, pages)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 2
    assert all(chunk.page_start <= chunk.page_end for chunk in chunks)


def test_unmapped_glyphs_never_reach_postgres_text():
    from app.services.knowledge_storage import clean_extracted_text
    assert clean_extracted_text("gross \x00 insurance\x07") == "gross – insurance "


@pytest.mark.asyncio
async def test_list_steps_under_a_toc_section_stay_body_text_and_year_titles_parse():
    toc = [("1. Quy dinh chung", 1), ("1.1. Cac buoc thuc te", 1), ("2. Bao hiem va thue 2026", 2)]
    body = [
        [("1. Quy dinh chung", 15), ("1.1. Cac buoc thuc te", 12), ("1. Mo bang cong va kiem tra.", 0),
         ("2. Gui don giai trinh.", 0), ("1.1.1. Truong hop dac biet", 11), ("Noi dung dac biet.", 0)],
        [("2. Bao hiem va thue 2026", 15), ("Muc dong bao hiem theo quy dinh hien hanh.", 0)],
    ]
    result = await build(make_pdf(toc=[toc], body=body))
    sections = by_heading(result)
    assert result.method == "PRINTED_TOC"
    assert "1. Mo bang cong va kiem tra." not in sections and "2. Gui don giai trinh." in sections["1.1. Cac buoc thuc te"].content
    assert sections["1.1.1. Truong hop dac biet"].heading_path.endswith("1.1. Cac buoc thuc te > 1.1.1. Truong hop dac biet")
    assert sections["2. Bao hiem va thue 2026"].page_start == 4


def test_parent_and_child_bookmarks_on_one_line_do_not_crash():
    from app.services.knowledge_ingest.models import Line
    from app.services.knowledge_ingest.structure import Anchor, _build
    pages = [[Line(1, "Phu luc 1. Mau don"), Line(1, "Noi dung mau don nghi phep")]]
    # The child is listed first on purpose: order must not depend on the outline order.
    # As _outline_anchors builds them: heading is the matched line, title the bookmark's own name.
    drafts = _build([Anchor(1, 0, "Phu luc 1. Mau don", 2, "Phu luc 1. Mau don"),
                     Anchor(1, 0, "Phu luc 1. Mau don", 1, "Phu luc")], pages, set())
    assert [(draft.heading, draft.heading_path) for draft in drafts] == [("Phu luc 1. Mau don", "Phu luc > Phu luc 1. Mau don")]
    assert "Noi dung mau don" in drafts[0].content
