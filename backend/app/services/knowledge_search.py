"""Hybrid retrieval over published chunks: vector + full-text + trigram, fused with RRF.

Permission filters are part of every SQL statement, so nothing a user may not
read is ranked, returned, or sent to the provider. Query embeddings are made
from the masked question only.
"""
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import and_, func, literal, literal_column, or_, select

from app.ai.providers.gemini import ProviderFailure, embed_texts, embeddings_ready
from app.core.config import settings
from app.models.knowledge import EMBEDDING_DIM, KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeSection
from app.services.ai_access import allowed_knowledge_roles
from app.services.knowledge_retrieval import Passage, normalize, tokens

logger = logging.getLogger(__name__)

RRF_K = 60
BRANCH_LIMIT = 20
TRIGRAM_MIN = 0.45
LEXICAL_MIN_OVERLAP = 0.35
BOOST_SECTION = 0.02
BOOST_RULE = 0.01


@dataclass
class SearchHit:
    passage: Passage
    normalized: str = ""
    score: float = 0.0
    branches: set[str] = field(default_factory=set)


def _visible(roles, today, *, rule_types=None, domains=None):
    """Conditions shared by all branches; identical to AIKnowledgeTool.documents for PDFs."""
    allowed = allowed_knowledge_roles(roles)
    conditions = [
        KnowledgeDocument.status == "PUBLISHED",
        KnowledgeDocument.minimum_role.in_(allowed),
        KnowledgeDocumentVersion.status == "PUBLISHED",
        KnowledgeDocumentVersion.minimum_role.in_(allowed),
        KnowledgeSection.is_answerable.is_(True),
        or_(KnowledgeDocumentVersion.effective_from.is_(None), KnowledgeDocumentVersion.effective_from <= today),
        or_(KnowledgeDocumentVersion.effective_to.is_(None), KnowledgeDocumentVersion.effective_to >= today),
    ]
    if rule_types:
        conditions.append(KnowledgeChunk.rule_type.in_(list(rule_types)))
    if domains:
        conditions.append(KnowledgeChunk.applies_to.overlap(list(domains)))
    return conditions


def _base(score, roles, today, **filters):
    return select(
        KnowledgeChunk.chunk_id.label("chunk_id"),
        KnowledgeChunk.section_id.label("section_id"),
        KnowledgeChunk.version_id.label("version_id"),
        KnowledgeDocument.document_id.label("document_id"),
        KnowledgeDocumentVersion.title.label("title"),
        KnowledgeChunk.content.label("content"),
        KnowledgeChunk.normalized_text.label("normalized_text"),
        KnowledgeChunk.page_start.label("page_start"),
        KnowledgeChunk.page_end.label("page_end"),
        KnowledgeChunk.rule_type.label("rule_type"),
        KnowledgeChunk.applies_to.label("applies_to"),
        KnowledgeSection.section_code.label("section_code"),
        KnowledgeSection.heading.label("heading"),
        score.label("score"),
    ).join(KnowledgeSection, KnowledgeSection.section_id == KnowledgeChunk.section_id
    ).join(KnowledgeDocumentVersion, KnowledgeDocumentVersion.version_id == KnowledgeChunk.version_id
    ).join(KnowledgeDocument, KnowledgeDocument.current_version_id == KnowledgeDocumentVersion.version_id
    ).where(and_(*_visible(roles, today, **filters)))


def _field(row, name, default=None):
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


def _passage(row) -> Passage:
    return Passage(
        document_id=_field(row, "document_id"), title=_field(row, "title"), content=_field(row, "content"),
        source_url=None, version_id=_field(row, "version_id"), section_id=_field(row, "section_id"),
        section_code=_field(row, "section_code"), heading=_field(row, "heading"),
        page_start=_field(row, "page_start"), page_end=_field(row, "page_end"),
        chunk_id=_field(row, "chunk_id"), rule_type=_field(row, "rule_type"),
        applies_to=list(_field(row, "applies_to") or []),
    )


async def _rows(db, statement):
    rows = (await db.execute(statement)).mappings().all()
    # Only chunk rows take part in fusion (never legacy document rows).
    return [row for row in rows if _field(row, "chunk_id") is not None]


async def _query_vectors(texts: list[str]) -> list[list[float]]:
    if not embeddings_ready():
        return []
    try:
        return await embed_texts("embed_query", texts, "RETRIEVAL_QUERY", dimensions=EMBEDDING_DIM)
    except ProviderFailure as exc:
        # Lexical branches still answer; no personal data is involved in this fallback.
        logger.info("knowledge_query_embedding_unavailable category=%s", exc.category)
        return []


async def hybrid_search(db, roles, today, queries: Sequence[str], *, embed_queries: Sequence[str] | None = None,
                        limit: int = 3, boost_section_ids: Sequence[int] = (), prefer_rule_types: Sequence[str] = (),
                        rule_types: Sequence[str] | None = None, domains: Sequence[str] | None = None) -> list[Passage]:
    """Rank authorized chunks for one question and its rewrites.

    embed_queries must already be masked; they default to no vector search.
    """
    queries = [query for query in dict.fromkeys(q.strip() for q in queries) if query]
    if db is None or not queries or limit <= 0:
        return []
    filters = {"rule_types": rule_types, "domains": domains}
    query_tokens = [tokens(query) for query in queries]
    all_tokens = sorted(set().union(*query_tokens))
    ranked_lists: dict[str, list] = {}

    if all_tokens:
        # Same 'simple' config as the generated search_tsv column; tokens are [a-z0-9]+ only.
        tsquery = func.to_tsquery(literal_column("'simple'"), " | ".join(all_tokens))
        rank = func.ts_rank_cd(KnowledgeChunk.search_tsv, tsquery)
        ranked_lists["fts"] = await _rows(db, _base(rank, roles, today, **filters)
                                          .where(KnowledgeChunk.search_tsv.op("@@")(tsquery))
                                          .order_by(rank.desc()).limit(BRANCH_LIMIT))
    # The user's own wording comes last; keep it alongside the first rewrites.
    trigram_queries = list(dict.fromkeys([queries[-1], *queries[:2]]))
    if trigram_queries:
        # `<%` can use the gin_trgm_ops index (a word_similarity() comparison cannot);
        # its threshold is a transaction-local setting.
        await db.execute(select(func.set_config("pg_trgm.word_similarity_threshold", str(TRIGRAM_MIN), True)))
    for index, query in enumerate(trigram_queries):
        normalized = literal(normalize(query))
        similarity = func.word_similarity(normalized, KnowledgeChunk.normalized_text)
        ranked_lists[f"trgm{index}"] = await _rows(db, _base(similarity, roles, today, **filters)
                                                   .where(normalized.op("<%")(KnowledgeChunk.normalized_text))
                                                   .order_by(similarity.desc()).limit(BRANCH_LIMIT))
    for index, vector in enumerate(await _query_vectors(list(embed_queries or [])[:4])):
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        ranked_lists[f"vec{index}"] = await _rows(db, _base(distance, roles, today, **filters)
                                                  .where(KnowledgeChunk.embedding.is_not(None),
                                                         distance <= settings.AI_KNOWLEDGE_VECTOR_MAX_DISTANCE)
                                                  .order_by(distance).limit(BRANCH_LIMIT))

    hits: dict[int, SearchHit] = {}
    for branch, rows in ranked_lists.items():
        for rank_index, row in enumerate(rows, 1):
            hit = hits.setdefault(_field(row, "chunk_id"), SearchHit(_passage(row), _field(row, "normalized_text") or ""))
            hit.score += 1 / (RRF_K + rank_index)
            hit.branches.add(branch[:3])
    boost = set(boost_section_ids)
    preferred = set(prefer_rule_types)
    selected: list[SearchHit] = []
    for hit in hits.values():
        if hit.branches == {"fts"}:
            # Full-text alone matches single common words; require real overlap.
            chunk_tokens = tokens(hit.normalized)
            best = max((len(q & chunk_tokens) / len(q) for q in query_tokens if q), default=0)
            if best < LEXICAL_MIN_OVERLAP:
                continue
        if hit.passage.section_id in boost:
            hit.score += BOOST_SECTION
        if hit.passage.rule_type in preferred:
            hit.score += BOOST_RULE
        query_heading = tokens(hit.passage.heading or "")
        hit.score += 0.002 * max((len(q & query_heading) for q in query_tokens), default=0)
        selected.append(hit)
    selected.sort(key=lambda hit: hit.score, reverse=True)
    result, seen_sections = [], set()
    for hit in selected:
        # One citation per section: show its best matching chunk once.
        if hit.passage.section_id in seen_sections:
            continue
        seen_sections.add(hit.passage.section_id)
        result.append(hit.passage)
        if len(result) >= limit:
            break
    return result


async def notice_documents(db, document_ids: Sequence[int]) -> list[dict]:
    """Full text of cited documents, only to detect draft/unconfirmed markers."""
    if db is None or not document_ids:
        return []
    rows = (await db.execute(select(KnowledgeDocument.document_id, KnowledgeDocument.content).where(
        KnowledgeDocument.document_id.in_(list(document_ids))))).mappings().all()
    return [{"document_id": _field(row, "document_id"), "content": _field(row, "content") or ""} for row in rows]
