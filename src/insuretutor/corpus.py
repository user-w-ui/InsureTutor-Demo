"""Frozen evidence, language-specific search views, and required-evidence assembly.

Offsets always address Unicode codepoints in evidence_text, never normalized text.
Search text is derived data and must not be used as a verbatim citation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from opencc import OpenCC
from pydantic import BaseModel, ConfigDict, Field, model_validator
from tokenizers import Tokenizer

from insuretutor.ingest.clean import expand_required, normalize

ROOT = Path(__file__).resolve().parents[2]
TOKENIZER_REPOSITORY = "intfloat/multilingual-e5-small"
TOKENIZER_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
TOKENIZER_SHA256 = "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
TOKENIZERS_VERSION = "0.21.4"
OPENCC_VERSION = "0.1.7"
TARGET_TOKENS = 256
MAX_TOKENS = 512
PREFIX = "passage: "
Language = Literal["zh-Hant", "en", "shared"]


class SourceSpan(BaseModel):
    """Retain every cleaner field, including raw text, bbox precision and origin."""

    model_config = ConfigDict(extra="allow")
    id: str
    source_key: str
    evidence_text: str
    language: str
    pdf_page: int = Field(ge=1)
    bbox_raw: list[int | float]
    text_origin: str
    quality_flags: list[str]


class LogicalUnit(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    kind: str
    text: str
    evidence_group: str
    source_span_ids: list[str]
    context_span_ids: list[str]
    requires: list[str]
    pages: list[int]
    indexable: bool
    conflict: bool = False
    pairing_status: str
    quality_flags: list[str]


class SourceSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    span_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    language: Language
    role: Literal["body", "context", "title", "header"] = "body"
    # Only a header has a cell_id: it names the cell this header qualifies.
    cell_id: str | None = None

    @model_validator(mode="after")
    def ordered(self) -> SourceSegment:
        if self.end <= self.start:
            raise ValueError("Empty or reversed source range")
        return self


class CellBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell: str
    column_headers: list[str]


class RetrievalView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    parent_unit_id: str
    language: Literal["zh-Hans", "en"]
    search_text: str
    source_segments: list[SourceSegment]
    token_count: int = Field(ge=1, le=MAX_TOKENS)


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    provenance: dict[str, Any]
    source_spans: list[SourceSpan]
    units: list[LogicalUnit]
    # Reviewed parent segmentation; view children may subdivide these ranges.
    language_segments: dict[str, list[SourceSegment]]
    context_by_unit: dict[str, list[str]]
    cell_bindings: dict[str, list[CellBinding]]
    parallel_units: dict[str, list[str]]
    retrieval_views: list[RetrievalView]

    @model_validator(mode="after")
    def references(self) -> Corpus:
        spans = {s.id: s for s in self.source_spans}
        units = {u.id: u for u in self.units}
        if len(spans) != len(self.source_spans) or len(units) != len(self.units):
            raise ValueError("Duplicate source or unit ID")
        if set(self.context_by_unit) != set(units) or set(self.cell_bindings) != set(units):
            raise ValueError("Context/binding unit IDs do not match corpus")
        for uid, peers in self.parallel_units.items():
            if uid not in units or set(peers) - units.keys() or uid in peers:
                raise ValueError("Dangling or self-referencing parallel unit")
            if any(uid not in self.parallel_units.get(peer, []) for peer in peers):
                raise ValueError("Parallel unit connection must be symmetric")
        for span in self.source_spans:
            parent = getattr(span, "parent_source_key", None)
            if parent and f"{self.provenance['source']['source_id']}/{parent}" not in spans:
                raise ValueError(f"Dangling source parent: {span.id}")
        referenced = set()
        for unit in self.units:
            if set(unit.requires) - units.keys():
                raise ValueError(f"Dangling requires: {unit.id}")
            ids = unit.source_span_ids + unit.context_span_ids + self.context_by_unit[unit.id]
            for binding in self.cell_bindings[unit.id]:
                if binding.cell not in unit.source_span_ids:
                    raise ValueError(f"Binding cell outside unit: {unit.id}")
                ids += binding.column_headers
            if set(ids) - spans.keys():
                raise ValueError(f"Dangling source/context: {unit.id}")
            referenced.update(ids)
        if set(self.language_segments) != referenced:
            raise ValueError("Missing or unexpected language segmentation")
        for sid, refs in self.language_segments.items():
            covered = set()
            for ref in refs:
                if ref.span_id != sid or ref.end > len(spans[sid].evidence_text):
                    raise ValueError(f"Invalid source range: {sid}")
                covered.update(range(ref.start, ref.end))
            text = spans[sid].evidence_text
            if any(i not in covered and not char.isspace() for i, char in enumerate(text)):
                raise ValueError(f"Language segmentation omitted source text: {sid}")
        view_ids = set()
        indexed_units = set()
        coverage: dict[tuple[str, str, str], set[int]] = {}
        for view in self.retrieval_views:
            if view.id in view_ids or view.parent_unit_id not in units:
                raise ValueError(f"Duplicate view or dangling parent: {view.id}")
            if not view.search_text.startswith(PREFIX):
                raise ValueError("Missing E5 passage prefix")
            if view.language == "en" and re.search(r"[\u3400-\u9fff\uf900-\ufaff]", view.search_text):
                raise ValueError(f"Chinese text in English view: {view.id}")
            view_ids.add(view.id)
            indexed_units.add(view.parent_unit_id)
            unit = units[view.parent_unit_id]
            permitted = set(unit.source_span_ids + self.context_by_unit[unit.id])
            for peer in self.parallel_units.get(unit.id, []):
                permitted.update(units[peer].source_span_ids)
            for binding in self.cell_bindings[unit.id]:
                permitted.update(binding.column_headers)
            for ref in view.source_segments:
                if ref.span_id not in permitted or ref.end > len(spans[ref.span_id].evidence_text):
                    raise ValueError(f"View source outside parent: {view.id}")
                expected_language = "zh-Hant" if view.language == "zh-Hans" else "en"
                if ref.language not in (expected_language, "shared"):
                    raise ValueError(f"Wrong language in view: {view.id}")
                if not any(ref.start >= p.start and ref.end <= p.end
                           and ref.language == p.language
                           for p in self.language_segments[ref.span_id]):
                    raise ValueError(f"View range outside reviewed segmentation: {view.id}")
                if ref.role == "header" and not any(
                    b.cell == ref.cell_id and ref.span_id in b.column_headers
                    for b in self.cell_bindings[unit.id]
                ):
                    raise ValueError(f"Unbound view header: {view.id}")
                coverage.setdefault((unit.id, view.language, ref.span_id), set()).update(
                    range(ref.start, ref.end))
        if indexed_units != {u.id for u in self.units if u.indexable}:
            raise ValueError("Indexable units missing views (or non-indexable units indexed)")
        for uid in indexed_units:
            if {v.language for v in self.retrieval_views if v.parent_unit_id == uid} != {"zh-Hans", "en"}:
                raise ValueError(f"Incomplete bilingual views: {uid}")
            unit = units[uid]
            expected_sources = unit.source_span_ids + self.context_by_unit[uid]
            for peer in self.parallel_units.get(uid, []):
                expected_sources += units[peer].source_span_ids
            bound = {b.cell: b.column_headers for b in self.cell_bindings[uid] if b.column_headers}
            for sid in dict.fromkeys(expected_sources):
                for part in self.language_segments[sid]:
                    languages = {"zh-Hans", "en"} if part.language == "shared" else {
                        "zh-Hans" if part.language == "zh-Hant" else "en"}
                    if part.language == "shared" and sid in bound:
                        languages &= {"zh-Hans" if language == "zh-Hant" else "en"
                            for h in bound[sid] for language in ("zh-Hant", "en")
                            if _matching(self.language_segments[h], language)}
                    for language in languages:
                        seen = coverage.get((uid, language, sid), set())
                        if any(i not in seen and not spans[sid].evidence_text[i].isspace()
                               for i in range(part.start, part.end)):
                            raise ValueError(f"View omitted source content: {uid}/{language}/{sid}")
        return self


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_unit_ids: list[str]
    units: list[LogicalUnit]
    source_spans: list[SourceSpan]
    context_by_unit: dict[str, list[str]]
    cell_bindings: dict[str, list[CellBinding]]
    language_segments: dict[str, list[SourceSegment]]
    parallel_units: dict[str, list[str]]
    conflicts: dict[str, str]
    quality_flags: dict[str, list[str]]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_bytes(corpus: Corpus) -> bytes:
    """Canonical UTF-8 output: no timestamps, paths of this machine or random IDs."""
    return (json.dumps(corpus.model_dump(mode="json"), ensure_ascii=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def load_tokenizer(path: Path = ROOT / "data/tokenizer/tokenizer.json") -> Tokenizer:
    if _sha(path) != TOKENIZER_SHA256:
        raise ValueError("E5 tokenizer hash does not match pinned revision")
    if version("tokenizers") != TOKENIZERS_VERSION:
        raise ValueError(f"Use tokenizers=={TOKENIZERS_VERSION} for reproducible lengths")
    tokenizer = Tokenizer.from_file(str(path))
    # Measure the entire input, including prefix and <s>/</s>. Never truncate/pad.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


def _language_parts(span: SourceSpan, rules: dict) -> list[SourceSegment]:
    if span.id in rules:
        rule = rules[span.id]
        if hashlib.sha256(span.evidence_text.encode()).hexdigest() != rule["evidence_sha256"]:
            raise ValueError(f"Stale language boundary: {span.id}")
        return [SourceSegment(span_id=span.id, **part) for part in rule["segments"]]
    if not span.evidence_text:
        return []
    if span.language == "mixed":
        raise ValueError(f"Mixed source requires a reviewed boundary: {span.id}")
    language = "shared" if span.language == "und" else span.language
    return [SourceSegment(span_id=span.id, start=0, end=len(span.evidence_text), language=language)]


def _slice(ref: SourceSegment, spans: dict[str, SourceSpan]) -> str:
    return spans[ref.span_id].evidence_text[ref.start:ref.end]


def _matching(parts: list[SourceSegment], language: str) -> list[SourceSegment]:
    return [p for p in parts if p.language in (language, "shared")]


def _body_parts(unit: LogicalUnit, segments: dict, spans: dict) -> list[SourceSegment]:
    verified = getattr(unit, "segments", [])
    if not verified:
        parts = [part for sid in unit.source_span_ids for part in segments[sid]]
        if unit.kind == "table_row" and len(unit.source_span_ids) > 1:
            # Keep row labels (including bilingual asset classes) on every child.
            parts = [p.model_copy(update={"role": "title"})
                     if getattr(spans[p.span_id], "table_col", None) == 0 else p for p in parts]
        return parts
    # Prefer the cleaner's PDF-verified title/body separation; never rewrite it.
    if {s["span_id"] for s in verified} != set(unit.source_span_ids):
        raise ValueError(f"Incomplete verified segments: {unit.id}")
    result = []
    for entry in verified:
        sid, title, body = entry["span_id"], entry["title"], entry["text"]
        text = spans[sid].evidence_text
        if text != title + ("\n" + body if body else ""):
            raise ValueError(f"Verified segment no longer matches evidence: {sid}")
        if body:
            result.append(SourceSegment(span_id=sid, start=0, end=len(title) + 1,
                                        language=entry["language"], role="title"))
            result.append(SourceSegment(span_id=sid, start=len(title) + 1, end=len(text),
                                        language=entry["language"]))
        else:
            result.extend(segments[sid])
    return result


def _views(unit: LogicalUnit, spans: dict, segments: dict, context: list[str],
           bindings: list[CellBinding], tokenizer: Tokenizer, cc: OpenCC,
           parallel_parts: list[SourceSegment] | None = None) -> list[RetrievalView]:
    body_parts = _body_parts(unit, segments, spans) + (parallel_parts or [])
    all_parts = body_parts + [p for sid in context for p in segments[sid]]
    languages = {p.language for p in all_parts} - {"shared"}
    if not languages:
        languages = {"zh-Hant", "en"}
    result = []
    bound = {b.cell: b.column_headers for b in bindings if b.column_headers}
    header_ids = {h for headers in bound.values() for h in headers}
    for language in ("zh-Hant", "en"):
        if language not in languages:
            continue
        body, titles = [], []
        for part in _matching(body_parts, language):
            # A neutral number in a Chinese-only table must keep its own column.
            if part.language == "shared" and part.span_id in bound and not any(
                _matching(segments[h], language) for h in bound[part.span_id]
            ):
                continue
            (titles if part.role == "title" else body).append(part)
        if not body:
            continue
        contextual = titles + [p.model_copy(update={"role": "context"})
                               for sid in context if sid not in header_ids
                               and sid not in unit.source_span_ids
                               for p in _matching(segments[sid], language)]

        def headers(parts):
            return [p.model_copy(update={"role": "header", "cell_id": cell})
                    for cell in dict.fromkeys(p.span_id for p in parts)
                    for sid in bound.get(cell, [])
                    for p in _matching(segments[sid], language)]

        def render(parts):
            # Join adjacent pieces from the same literal cell before normalization.
            rows = []
            for collection in (contextual, parts):
                for cell in dict.fromkeys(p.span_id for p in collection):
                    cell_parts = [p for p in collection if p.span_id == cell]
                    value, previous = "", None
                    for p in cell_parts:
                        if previous is not None and previous.end != p.start:
                            value += " "
                        value += _slice(p, spans)
                        previous = p
                    head = " ".join(_slice(h, spans) for h in headers(cell_parts))
                    rows.append((head + ": " if head else "") + value)
            text = "\n".join(rows)
            # Presentation normalization only. Source ranges and evidence stay literal.
            reviewed_numbers = {n for p in contextual + parts + headers(contextual + parts)
                                for n in getattr(spans[p.span_id], "note_refs", [])}
            present = {int(m.group(1) or m.group(2)) for m in re.finditer(
                r"<sup>(\d+)</sup>|\$\^\{(\d+)\}\$", text)}
            text = normalize(text, markup_refs=present & reviewed_numbers)[0]
            if language == "zh-Hant":
                text = cc.convert(text)
            return PREFIX + text

        def count(parts):
            return len(tokenizer.encode(render(parts), add_special_tokens=True).ids)

        if count(body) <= TARGET_TOKENS:
            chunks = [body]
        else:
            atoms = []
            for part in body:
                text = _slice(part, spans)
                boundaries = [0] + [m.end() for m in re.finditer(
                    r"[。！？；\n]+|[.!?;](?=\s|$)", text)] + [len(text)]
                for start, end in zip(boundaries, boundaries[1:]):
                    if end > start:
                        atom = part.model_copy(update={"start": part.start + start,
                                                       "end": part.start + end})
                        atoms.extend(_fit_atom(atom, count, spans))
            chunks, current = [], []
            for atom in atoms:
                if current and count(current + [atom]) > TARGET_TOKENS:
                    chunks.append(current)
                    current = []
                current.append(atom)
            if current:
                chunks.append(current)
        for i, parts in enumerate(chunks, 1):
            text = render(parts)
            refs = contextual + headers(contextual + parts) + parts
            view_language = "zh-Hans" if language == "zh-Hant" else "en"
            result.append(RetrievalView(id=f"{unit.id}/{view_language}/{i:03d}",
                parent_unit_id=unit.id, language=view_language, search_text=text,
                source_segments=refs, token_count=len(tokenizer.encode(text).ids)))
    return result


def _fit_atom(atom: SourceSegment, count, spans: dict) -> list[SourceSegment]:
    """Split only an oversized sentence, at phrase/word boundaries where possible."""
    result = []
    while count([atom]) > MAX_TOKENS:
        text = _slice(atom, spans)
        boundaries = [m.end() for m in re.finditer(r"[,，、:：]\s*|\s+", text)]
        fitting = [end for end in boundaries if end < len(text) and count([
            atom.model_copy(update={"end": atom.start + end})]) <= TARGET_TOKENS]
        if not fitting:
            # No usable phrase boundary: preserve every codepoint, never truncate.
            # This finite scan also handles non-monotonic tokenizer lengths safely.
            fitting = [end for end in range(1, len(text)) if count([
                atom.model_copy(update={"end": atom.start + end})]) <= TARGET_TOKENS]
        if not fitting:
            raise ValueError(f"Context leaves no space for body: {atom.span_id}")
        end = atom.start + max(fitting)
        result.append(atom.model_copy(update={"end": end}))
        atom = atom.model_copy(update={"start": end})
    result.append(atom)
    return result


def build_corpus(cleaned_dir: Path = ROOT / "data/cleaned",
                 rules_path: Path = ROOT / "data/corpus-rules.json",
                 tokenizer_path: Path = ROOT / "data/tokenizer/tokenizer.json") -> Corpus:
    """Build with pinned local inputs. No HTTP, embedding weights or model API."""
    cleaned_dir, rules_path, tokenizer_path = map(Path, (cleaned_dir, rules_path, tokenizer_path))
    manifest = json.loads((cleaned_dir / "manifest.json").read_text(encoding="utf-8"))
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    if rules["schema_version"] != 1:
        raise ValueError("Unsupported corpus rules schema")
    for filename, key in [("units.jsonl", "cleaned_units_sha256"),
                          ("spans.jsonl", "cleaned_spans_sha256")]:
        if _sha(cleaned_dir / filename) != rules[key] or rules[key] != manifest["artifacts"][filename]:
            raise ValueError(f"Cleaned input changed; review boundaries: {filename}")
    if version("opencc-python-reimplemented") != OPENCC_VERSION:
        raise ValueError(f"Use opencc-python-reimplemented=={OPENCC_VERSION}")
    source_spans = [SourceSpan.model_validate_json(line) for line in
                    (cleaned_dir / "spans.jsonl").read_text(encoding="utf-8").splitlines()]
    units = [LogicalUnit.model_validate_json(line) for line in
             (cleaned_dir / "units.jsonl").read_text(encoding="utf-8").splitlines()]
    spans = {s.id: s for s in source_spans}
    known_units = {u.id for u in units}
    if (set(rules["unit_context"]) | set(rules["cell_bindings"])) - known_units:
        raise ValueError("Corpus rules reference unknown units")
    if set(rules["spans"]) - spans.keys():
        raise ValueError("Corpus rules reference unknown sources")
    context, bindings = {}, {}
    for unit in units:
        context[unit.id] = list(dict.fromkeys(unit.context_span_ids
                                            + rules["unit_context"].get(unit.id, [])))
        raw_bindings = getattr(unit, "cell_bindings", []) + rules["cell_bindings"].get(unit.id, [])
        bindings[unit.id] = [CellBinding.model_validate(b) for b in raw_bindings]
        for binding in bindings[unit.id]:
            context[unit.id] = list(dict.fromkeys(context[unit.id] + binding.column_headers))
    referenced = {sid for unit in units for sid in unit.source_span_ids + context[unit.id]}
    segments = {sid: _language_parts(spans[sid], rules["spans"]) for sid in sorted(referenced)}
    tokenizer = load_tokenizer(tokenizer_path)
    cc = OpenCC("t2s")
    views = [view for unit in units if unit.indexable
             for view in _views(unit, spans, segments, context[unit.id], bindings[unit.id], tokenizer, cc,
                 [part for peer in rules["parallel_units"].get(unit.id, [])
                  for part in _body_parts(next(u for u in units if u.id == peer), segments, spans)])]
    return Corpus(provenance={
        "source": manifest,
        "corpus_rules_sha256": _sha(rules_path),
        "builder_sha256": _sha(Path(__file__)),
        "tokenizer": {"repository": TOKENIZER_REPOSITORY, "revision": TOKENIZER_REVISION,
                      "sha256": TOKENIZER_SHA256, "library": "tokenizers",
                      "library_version": TOKENIZERS_VERSION, "add_special_tokens": True,
                      "prefix": PREFIX, "target_tokens": TARGET_TOKENS, "max_tokens": MAX_TOKENS},
        "normalization": {"version": 1, "opencc": "t2s", "opencc_version": OPENCC_VERSION,
                          "cleaner_sha256": _sha(Path(__file__).parent / "ingest/clean.py")},
    }, source_spans=source_spans, units=units, language_segments=segments,
        context_by_unit=context, cell_bindings=bindings, parallel_units=rules["parallel_units"],
        retrieval_views=views)


def assemble_evidence(corpus: Corpus, unit_ids: list[str]) -> EvidenceBundle:
    """Recover full parents, recursively expand cleaner requires, then dedup sources.

    evidence_group is descriptive metadata; distinct unit IDs remain distinct facts.
    Conflict units retain all language sources regardless of the matched child view.
    """
    selected = list(dict.fromkeys(unit_ids))
    lookup = {u.id: u for u in corpus.units}
    unknown = set(selected) - lookup.keys()
    if unknown:
        raise ValueError(f"Unknown evidence unit IDs: {sorted(unknown)}")
    seeds = selected[:]
    while True:
        expanded = expand_required([u.model_dump() for u in corpus.units], seeds)
        expanded_ids = {u["id"] for u in expanded}
        missing_peers = list(dict.fromkeys(peer for u in expanded
            for peer in corpus.parallel_units.get(u["id"], []) if peer not in expanded_ids))
        if not missing_peers:
            break
        seeds.extend(missing_peers)
    units = [lookup[u["id"]] for u in expanded]
    source_ids = list(dict.fromkeys(sid for unit in units
                                   for sid in unit.source_span_ids + corpus.context_by_unit[unit.id]))
    spans = {s.id: s for s in corpus.source_spans}
    flags = {obj.id: obj.quality_flags for obj in units + [spans[s] for s in source_ids]
             if obj.quality_flags}
    return EvidenceBundle(selected_unit_ids=selected, units=units,
        source_spans=[spans[sid] for sid in source_ids],
        context_by_unit={u.id: corpus.context_by_unit[u.id] for u in units},
        cell_bindings={u.id: corpus.cell_bindings[u.id] for u in units},
        language_segments={sid: corpus.language_segments[sid] for sid in source_ids},
        parallel_units={u.id: corpus.parallel_units[u.id] for u in units if u.id in corpus.parallel_units},
        conflicts={u.id: getattr(u, "conflict_detail", "") for u in units if u.conflict},
        quality_flags=flags)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/corpus.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / "raw data") \
            or output.is_relative_to(ROOT / "data/cleaned"):
        parser.error("Output must be in this workspace, outside raw data and data/cleaned")
    corpus = build_corpus()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(corpus_bytes(corpus))
    print(f"Built {len(corpus.units)} units, {len(corpus.retrieval_views)} views -> {output}")


if __name__ == "__main__":
    main()
