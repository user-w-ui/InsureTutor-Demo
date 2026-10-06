"""Web reference groups derived only from a completed turn's server citations."""

import re
from typing import Literal

from pydantic import Field

from insuretutor.chat_models import ChatResult, Citation, StrictModel
from insuretutor.corpus import Corpus, LanguageRecord, SourceSpan, assemble_evidence


class ReferenceSource(Citation):
    role: Literal["body", "context"]


class ReferenceVersion(StrictModel):
    language: Literal["en", "zh-Hant"]
    title: str
    sources: list[ReferenceSource]


class ReferenceGroup(StrictModel):
    unit_id: str
    conflict: bool
    required_unit_ids: list[str]
    versions: list[ReferenceVersion]


class ChatResponse(ChatResult):
    reference_groups: list[ReferenceGroup] = Field(default_factory=list)


def display_title(uid: str, record: LanguageRecord, spans: dict[str, SourceSpan]) -> str:
    """Shared reference/progress label: the record title or a short first source line."""
    if record.title:
        return record.title
    note = re.fullmatch(r"note-(\d+)", uid)
    if note:
        return f"Note {note[1]}" if record.language == "en" else f"附註 {note[1]}"
    # Use a source excerpt rather than invent a semantic title.
    title = spans[record.source_span_ids[0]].evidence_text.splitlines()[0]
    return title[:80] + ("…" if len(title) > 80 else "")


def with_references(result: ChatResult, corpus: Corpus) -> ChatResponse:
    spans = {s.id: s for s in corpus.source_spans}
    units = {u.id: u for u in corpus.units}
    allowed = {uid for citation in result.citations for uid in citation.unit_ids}
    # Guard against an adapter accidentally linking a fabricated or stale result.
    for citation in result.citations:
        span = spans.get(citation.span_id)
        if span is None or citation.quote != span.evidence_text:
            raise ValueError("Citation does not address the current corpus")
        if any(uid not in units for uid in citation.unit_ids):
            raise ValueError("Unknown cited unit")
    if any(uid not in allowed for claim in result.claims for uid in claim.evidence_ids):
        raise ValueError("Claim lacks a delivered citation")
    order = list(
        dict.fromkeys(
            [uid for claim in result.claims for uid in claim.evidence_ids]
            + [uid for citation in result.citations for uid in citation.unit_ids]
        )
    )
    bundle = assemble_evidence(corpus, order)
    order += [u.id for u in bundle.units if u.id not in order]
    source_id = corpus.provenance["source"]["source_id"]
    groups = []
    for uid in order:
        unit = units[uid]
        closure = assemble_evidence(corpus, [uid])
        versions = []
        for record in unit.segments:
            sources = []
            for sid in dict.fromkeys(record.source_span_ids + corpus.context_by_unit[uid]):
                span = spans[sid]
                if span.language != record.language:
                    continue
                sources.append(
                    ReferenceSource(
                        unit_ids=[uid],
                        span_id=sid,
                        quote=span.evidence_text,
                        pdf_page=span.pdf_page,
                        language=span.language,
                        source_id=source_id,
                        source_url=f"/sources/{source_id}.pdf#page={span.pdf_page}",
                        bbox_raw=span.bbox_raw,
                        text_origin=span.text_origin,
                        origin_span_id=getattr(span, "origin_span_id", None),
                        origin_ranges=getattr(span, "origin_ranges", []),
                        bbox_precision=getattr(span, "bbox_precision", None),
                        quality_flags=span.quality_flags,
                        role="body" if sid in record.source_span_ids else "context",
                    )
                )
            versions.append(
                ReferenceVersion(
                    language=record.language,
                    title=display_title(uid, record, spans),
                    sources=sources,
                )
            )
        groups.append(
            ReferenceGroup(
                unit_id=uid,
                conflict=unit.conflict,
                required_unit_ids=[u.id for u in closure.units if u.id != uid],
                versions=versions,
            )
        )
    return ChatResponse(**result.model_dump(), reference_groups=groups)
