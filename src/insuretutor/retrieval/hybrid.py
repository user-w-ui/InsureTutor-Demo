"""The sole asynchronous retrieval boundary and its small in-memory implementation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict
from rank_bm25 import BM25Okapi

from insuretutor.corpus import Corpus, EvidenceBundle, assemble_evidence

from .embedding import MODEL_DIR, LocalE5Encoder, normalize_search, validate_vectors
from .index import CORPUS_PATH, INDEX_DIR, load_corpus, load_index
from .lexical import lexical_tokens, verified_terms


class QueryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_question: str
    rewritten_query: str | None = None
    response_language: Literal["auto", "en", "zh-Hans", "zh-Hant"] = "auto"
    # Initial tutor retrieval expands a multi-sentence question so one long clause
    # cannot crowd the others out of the channel top-k. Supplemental agent searches
    # pass False: the query the model submitted is retrieved verbatim.
    expand_sentences: bool = False


class Retriever(Protocol):
    async def retrieve(self, context: QueryContext) -> EvidenceBundle: ...


class QueryEncoder(Protocol):
    def encode_queries(self, texts: list[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class RankedUnit:
    unit_id: str
    score: float


@dataclass(frozen=True)
class Rankings:
    bm25: list[RankedUnit]
    vector: list[RankedUnit]
    hybrid: list[RankedUnit]


# Both fullwidth and halfwidth terminators. Commas are deliberately absent: a
# comma often separates a benefit from the condition that qualifies it.
SENTENCE_BREAK = re.compile(r"(?<=[。！？!?；;])")
MAX_QUERY_SENTENCES = 4
MIN_SENTENCE_CHARACTERS = 6


def query_sentences(question: str) -> list[str]:
    """Split a question on sentence terminators, bounded and noise-filtered.

    Split before normalization: NFKC folds the fullwidth terminators this relies
    on into their ASCII forms, so splitting afterwards would never match Chinese.
    Returns [question] unchanged when there is nothing useful to split, so the
    single-sentence path stays byte-identical to unexpanded retrieval.
    """
    raw = [part.strip() for part in SENTENCE_BREAK.split(question)]
    parts = [normalize_search(part) for part in raw if part.strip()]
    if len(parts) < 2:
        return [normalize_search(question)]
    # Short leading fragments ("我要增加基本保障额。") are premises, not questions;
    # they only add noise as standalone queries.
    kept = [part for part in parts if len(part) >= MIN_SENTENCE_CHARACTERS]
    if len(kept) < 2:
        return [normalize_search(question)]
    return kept[:MAX_QUERY_SENTENCES]


def fuse(bm25: list[RankedUnit], vector: list[RankedUnit], constant: int = 60) -> list[RankedUnit]:
    scores: dict[str, float] = {}
    for channel in (bm25, vector):
        for rank, unit in enumerate(channel, 1):
            scores[unit.unit_id] = scores.get(unit.unit_id, 0) + 1 / (constant + rank)
    return sorted(
        (RankedUnit(uid, score) for uid, score in scores.items()),
        key=lambda item: (-item.score, item.unit_id),
    )


class HybridRetriever:
    def __init__(
        self,
        corpus: Corpus,
        vectors: np.ndarray,
        encoder: QueryEncoder,
        *,
        channel_top_k: int = 12,
        top_k: int = 8,
        character_budget: int = 12_000,
        rrf_constant: int = 60,
    ):
        validate_vectors(vectors, len(corpus.retrieval_views))
        if min(channel_top_k, top_k, character_budget, rrf_constant) <= 0:
            raise ValueError("Retrieval limits must be positive")
        self.corpus, self.vectors, self.encoder = corpus, vectors, encoder
        self.channel_top_k, self.top_k = channel_top_k, top_k
        self.character_budget, self.rrf_constant = character_budget, rrf_constant
        self.terms = verified_terms(corpus)
        self.tokens = [lexical_tokens(v.search_text, self.terms) for v in corpus.retrieval_views]
        self.bm25 = BM25Okapi(self.tokens)
        self.encode_lock = asyncio.Lock()

    @classmethod
    def from_local(
        cls,
        corpus_path: Path = CORPUS_PATH,
        index_dir: Path = INDEX_DIR,
        model_dir: Path = MODEL_DIR,
        threads: int = 2,
        **options,
    ) -> HybridRetriever:
        corpus = load_corpus(corpus_path)
        vectors = load_index(corpus, corpus_path, index_dir)
        return cls(corpus, vectors, LocalE5Encoder(model_dir, threads), **options)

    def _collapse(self, scores: np.ndarray, *, positive_only: bool) -> list[RankedUnit]:
        best: dict[str, float] = {}
        for view, score in zip(self.corpus.retrieval_views, scores, strict=True):
            value = float(score)
            if positive_only and value <= 0:
                continue
            best[view.parent_unit_id] = max(best.get(view.parent_unit_id, -float("inf")), value)
        return sorted(
            (RankedUnit(uid, score) for uid, score in best.items()),
            key=lambda item: (-item.score, item.unit_id),
        )[: self.channel_top_k]

    @staticmethod
    def _queries(context: QueryContext) -> list[str]:
        """Every query text this retrieval will encode, in stable order."""
        queries: list[str] = []
        for variant in (context.original_question, context.rewritten_query):
            if not variant or not variant.strip():
                continue
            if context.expand_sentences:
                queries.extend(query_sentences(variant))
            else:
                queries.append(normalize_search(variant))
        return list(dict.fromkeys(queries))

    def _per_query(self, scores_per_query: np.ndarray, *, positive_only: bool) -> list[RankedUnit]:
        """Collapse each query independently, then vote by rank across queries.

        Scores from different queries share no scale (a short sentence and a long
        question produce wildly different BM25 magnitudes), so they are merged by
        position rather than by value. A unit ranked first by any single sentence
        earns the same vote it would have earned from a whole-question match.
        """
        votes: dict[str, float] = {}
        for row in scores_per_query:
            for rank, unit in enumerate(self._collapse(row, positive_only=positive_only), 1):
                votes[unit.unit_id] = votes.get(unit.unit_id, 0) + 1 / (self.rrf_constant + rank)
        return sorted(
            (RankedUnit(uid, score) for uid, score in votes.items()),
            key=lambda item: (-item.score, item.unit_id),
        )[: self.channel_top_k]

    async def rank(self, context: QueryContext) -> Rankings:
        """Diagnostics for CLI/evaluation; Tutor uses retrieve() exclusively."""
        queries = self._queries(context)
        if not queries:
            return Rankings([], [], [])
        # Encoding remains serialized across callers; cancellation must not release the
        # lock while an uncancellable worker is still executing the ONNX session.
        async with self.encode_lock:
            task = asyncio.create_task(asyncio.to_thread(self.encoder.encode_queries, queries))
            try:
                query_vectors = await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
        validate_vectors(query_vectors, len(queries))
        lexical = np.array(
            [self.bm25.get_scores(lexical_tokens(q, self.terms)) for q in queries], dtype=float
        )
        dense = np.array([self.vectors @ vector for vector in query_vectors], dtype=float)
        bm25 = self._per_query(lexical, positive_only=True)
        vector = self._per_query(dense, positive_only=False)
        return Rankings(bm25, vector, fuse(bm25, vector, self.rrf_constant))

    def evidence_for(self, ranked: list[RankedUnit]) -> EvidenceBundle:
        """Greedy whole-closure budget: automatic additions never consume top-k."""
        selected: list[str] = []
        bundle = assemble_evidence(self.corpus, [])
        included: set[str] = set()
        for candidate in ranked:
            if len(selected) >= self.top_k:
                break
            if candidate.unit_id in included:
                continue
            proposed = assemble_evidence(self.corpus, selected + [candidate.unit_id])
            if sum(len(s.evidence_text) for s in proposed.source_spans) > self.character_budget:
                continue
            selected.append(candidate.unit_id)
            bundle = proposed
            included = {u.id for u in bundle.units}
        return bundle

    async def retrieve(self, context: QueryContext) -> EvidenceBundle:
        return self.evidence_for((await self.rank(context)).hybrid)
