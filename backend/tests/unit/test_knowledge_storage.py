from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, TextStringObject
from reportlab.pdfgen import canvas

from app.core import config
from app.services.knowledge_storage import (
    PDFValidationError,
    delete_pdf,
    parse_pdf,
    resolve_storage_path,
    store_pdf,
)


def make_pdf(text="Leave Policy"):
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=(612, 792))
    page.setFont("Helvetica", 12)
    page.drawString(40, 740, text)
    page.save()
    return output.getvalue()


def test_parser_extracts_text_and_checks_hash():
    data = make_pdf()
    parsed = parse_pdf(data)
    assert parsed.pages == ["Leave Policy"]
    assert parsed.byte_size == len(data)
    assert len(parsed.sha256) == 64
    assert parsed.mime_type == "application/pdf"


def test_parser_rejects_invalid_encrypted_active_and_empty_pdfs():
    with pytest.raises(PDFValidationError, match="PDF_MIME_INVALID"):
        parse_pdf(b"not a pdf")

    encrypted = BytesIO()
    canvas.Canvas(encrypted, encrypt="password").save()
    with pytest.raises(PDFValidationError, match="PDF_ENCRYPTED"):
        parse_pdf(encrypted.getvalue())

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_js("app.alert('blocked')")
    active = BytesIO()
    writer.write(active)
    with pytest.raises(PDFValidationError, match="PDF_ACTIVE_CONTENT"):
        parse_pdf(active.getvalue())

    blank = BytesIO()
    empty_page = canvas.Canvas(blank)
    empty_page.showPage()
    empty_page.save()
    with pytest.raises(PDFValidationError, match="PDF_TEXT_REQUIRED"):
        parse_pdf(blank.getvalue())


def test_private_storage_uses_server_key_and_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "AI_KNOWLEDGE_STORAGE_DIR", tmp_path)
    data = make_pdf()
    key = store_pdf(data)
    path = resolve_storage_path(key)
    assert path.parent == tmp_path.resolve()
    assert path.read_bytes() == data
    with pytest.raises(FileNotFoundError):
        resolve_storage_path("../secret.pdf")
    delete_pdf(key)
    assert not path.exists()


def test_parser_enforces_size_limit():
    with pytest.raises(PDFValidationError, match="PDF_SIZE_INVALID"):
        parse_pdf(make_pdf(), max_bytes=10)


@pytest.mark.parametrize("event", ["/O", "/PO"])
@pytest.mark.parametrize("chained", [False, True])
def test_parser_rejects_nested_additional_actions(event, chained):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(make_pdf())))
    forbidden = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert(1)"),
    })
    action = DictionaryObject({NameObject("/S"): NameObject("/GoTo"), NameObject("/Next"): writer._add_object(forbidden)}) if chained else forbidden
    writer.pages[0][NameObject("/AA")] = DictionaryObject({NameObject(event): writer._add_object(action)})
    output = BytesIO()
    writer.write(output)
    with pytest.raises(PDFValidationError, match="PDF_ACTIVE_CONTENT"):
        parse_pdf(output.getvalue())


def test_action_chains_preserve_cycle_protection_and_check_all_branches():
    from app.services.knowledge_storage import _contains_forbidden_action
    safe = {"/S": "/GoTo"}
    safe["/Next"] = safe
    assert not _contains_forbidden_action(safe)
    safe["/Next"] = [safe, {"/S": "/Launch"}]
    assert _contains_forbidden_action(safe)


@pytest.mark.parametrize("location", ["xfa", "field_action", "outline_action"])
def test_parser_rejects_active_content_in_form_and_outline_objects(location):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(make_pdf())))
    forbidden = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert(1)"),
    })
    if location == "xfa":
        xfa = DecodedStreamObject()
        xfa.set_data(b'<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/"/>')
        form = DictionaryObject({
            NameObject("/Fields"): ArrayObject(), NameObject("/XFA"): writer._add_object(xfa),
        })
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(form)
    elif location == "field_action":
        field = DictionaryObject({
            NameObject("/FT"): NameObject("/Tx"), NameObject("/T"): TextStringObject("hidden"),
            NameObject("/AA"): DictionaryObject({NameObject("/C"): writer._add_object(forbidden)}),
        })
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(DictionaryObject({
            NameObject("/Fields"): ArrayObject([writer._add_object(field)]),
        }))
    else:
        outline = writer.add_outline_item("Policy", 0)
        outline.get_object()[NameObject("/A")] = writer._add_object(forbidden)
    output = BytesIO()
    writer.write(output)
    with pytest.raises(PDFValidationError, match="PDF_ACTIVE_CONTENT"):
        parse_pdf(output.getvalue())


def test_parser_allows_safe_bookmarks():
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(make_pdf())))
    writer.add_outline_item("Leave Policy", 0)
    output = BytesIO()
    writer.write(output)
    assert parse_pdf(output.getvalue()).pages == ["Leave Policy"]


def test_object_graph_traversal_handles_nested_cycles_and_deep_structures():
    from app.services.knowledge_storage import _contains_forbidden_action
    root = {"/AcroForm": {"/Fields": []}}
    root["/AcroForm"]["/Fields"].append(root)
    assert not _contains_forbidden_action(root)
    root["/AcroForm"]["/Fields"].append({"/S": "/Launch"})
    assert _contains_forbidden_action(root)
    nested = {"/S": "/JavaScript"}
    for _ in range(1500):
        nested = {"/First": nested}
    assert _contains_forbidden_action(nested)
