"""Dynamic PDF ingestion: layout → structure (outline, printed TOC, fonts) → chunks."""
from app.services.knowledge_ingest.models import Line, SectionDraft, StructureResult
from app.services.knowledge_ingest.text import compact, heading_matches

__all__ = ["Line", "SectionDraft", "StructureResult", "compact", "heading_matches"]
