from dataclasses import dataclass, field


@dataclass
class Line:
    page: int  # 1-based PDF page index
    text: str
    size: float | None = None  # median font size; None when only plain text is available
    bold: bool = False
    top: float = 0.0
    x0: float = 0.0
    page_height: float = 0.0


@dataclass
class SectionDraft:
    section_code: str
    heading: str
    page_start: int
    page_end: int
    content: str
    level: int = 1
    heading_path: str = ""
    is_answerable: bool = True


@dataclass
class StructureResult:
    sections: list[SectionDraft]
    method: str  # OUTLINE | PRINTED_TOC | LAYOUT | PAGE | GEMINI_STRUCTURE | GEMINI_OCR
    toc_pages: set[int] = field(default_factory=set)
