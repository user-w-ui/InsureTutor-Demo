"""Retrieval contracts with fake encoding: no weights, downloads or model API."""

import asyncio
import json
import shutil
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from opencc import OpenCC

from insuretutor.corpus import ROOT, assemble_evidence, load_tokenizer
from insuretutor.retrieval import HybridRetriever, QueryContext
from insuretutor.retrieval.embedding import (
    DIMENSION,
    LocalE5Encoder,
    prefixed,
    sha256,
)
from insuretutor.retrieval.hybrid import RankedUnit, fuse
from insuretutor.retrieval.index import build_index, load_corpus, load_index
from insuretutor.retrieval.lexical import lexical_tokens


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


@pytest.fixture
def artifact_dir():
    # Workspace scratch with inherited ACLs also works in restricted Windows shells.
    root = (ROOT / "tmp/retrieval-tests").resolve()
    directory = root / uuid.uuid4().hex
    directory.mkdir(parents=True)
    yield directory
    assert directory.resolve().is_relative_to(root)
    shutil.rmtree(directory)


class FakeEncoder:
    def __init__(self):
        self.texts = []
        self.thread = None

    def encode_queries(self, texts):
        self.texts = texts
        self.thread = threading.get_ident()
        vectors = np.zeros((len(texts), DIMENSION), dtype=np.float32)
        vectors[:, 0] = 1
        return vectors

    encode_documents = encode_queries


def make_retriever(corpus, **kwargs):
    encoder = FakeEncoder()
    vectors = encoder.encode_documents([v.search_text for v in corpus.retrieval_views])
    return HybridRetriever(corpus, vectors, encoder, **kwargs)


def test_views_languages_and_rewrites_collapse_before_fusion(corpus):
    retriever = make_retriever(corpus)
    scores = np.zeros(len(corpus.retrieval_views))
    for i, view in enumerate(corpus.retrieval_views):
        if view.parent_unit_id == "insurability":
            scores[i] = 100 + i
        if view.parent_unit_id == "enhancement":
            scores[i] = 50
    collapsed = retriever._collapse(scores, positive_only=True)
    assert [r.unit_id for r in collapsed] == ["insurability", "enhancement"]
    results = fuse(collapsed, collapsed)
    assert results[0].score == 2 / 61  # Not one vote per language or child.
    context = QueryContext(
        original_question="保證可保權益", rewritten_query="marriage option", response_language="en"
    )
    asyncio.run(retriever.rank(context))
    assert retriever.encoder.texts == ["保证可保权益", "marriage option"]
    assert retriever.encoder.thread != threading.get_ident()


def test_stable_unit_ties_and_unmatched_bm25(corpus):
    retriever = make_retriever(corpus)
    result = asyncio.run(retriever.rank(QueryContext(original_question="zzzzqxvv")))
    assert result.bm25 == []
    assert [r.unit_id for r in result.vector] == sorted({u.id for u in corpus.units})[:12]
    tied = fuse([RankedUnit("b", 1)], [RankedUnit("a", 1)])
    assert [r.unit_id for r in tied] == ["a", "b"]


def test_traditional_simplified_and_response_language_do_not_filter(corpus):
    retriever = make_retriever(corpus)
    traditional = "保證可保權益每次增加25%，最多兩次"
    simplified = OpenCC("t2s").convert(traditional)
    first = asyncio.run(
        retriever.rank(QueryContext(original_question=traditional, response_language="en"))
    )
    second = asyncio.run(
        retriever.rank(QueryContext(original_question=simplified, response_language="zh-Hant"))
    )
    assert first == second
    assert lexical_tokens("Guaranteed 保證可保權益")
    assert "guaranteed" in lexical_tokens("Guaranteed 保證可保權益")


@pytest.mark.parametrize(
    "a,b,token",
    [
        ("HK$400,000", "400000港元", "amount:hkd:400000"),
        ("US$1,000,000", "1000000美元", "amount:usd:1000000"),
        ("MOP4,000", "4000澳門元", "amount:mop:4000"),
        ("2.750%", "2.75 percent", "percent:2.75"),
    ],
)
def test_numeric_and_currency_equivalence(a, b, token):
    assert token in lexical_tokens(a) and token in lexical_tokens(b)


def test_number_currency_and_heading_match_real_bm25(corpus):
    retriever = make_retriever(corpus)
    result = asyncio.run(
        retriever.rank(QueryContext(original_question="HK$40,000 increase decrease"))
    )
    assert "table-354-row-5" in [r.unit_id for r in result.bm25[:5]]
    assert lexical_tokens("保证可保权益", retriever.terms)[-1] == "term:b88"
    assert lexical_tokens("Guaranteed Insurability Option", retriever.terms)[-1] == "term:b88"


def test_footnote_independent_ranking_and_mandatory_body_closure(corpus):
    retriever = make_retriever(corpus, top_k=1)
    independent = retriever.evidence_for([RankedUnit("note-3", 1)])
    assert independent.selected_unit_ids == ["note-3"]
    assert "insurability" not in {u.id for u in independent.units}
    restored = retriever.evidence_for([RankedUnit("withdrawal", 1)])
    assert restored.selected_unit_ids == ["withdrawal"]
    assert {"withdrawal", "cash-value-risk", "term-and-lapse", "note-6", "note-7"} <= {
        u.id for u in restored.units
    }
    source = {s.id: s for s in corpus.source_spans}
    assert all(s == source[s.id] for s in restored.source_spans)


def test_automatic_notes_do_not_spend_top_k_or_duplicate_sources(corpus):
    retriever = make_retriever(corpus, top_k=2)
    bundle = retriever.evidence_for(
        [RankedUnit("insurability", 3), RankedUnit("note-3", 2), RankedUnit("enhancement", 1)]
    )
    assert bundle.selected_unit_ids == ["insurability", "enhancement"]
    assert len({s.id for s in bundle.source_spans}) == len(bundle.source_spans)


def test_budget_skips_whole_closure_and_keeps_later_small_candidate(corpus):
    needed = assemble_evidence(corpus, ["withdrawal"])
    budget = sum(len(s.evidence_text) for s in needed.source_spans) - 1
    retriever = make_retriever(corpus, character_budget=budget)
    result = retriever.evidence_for([RankedUnit("withdrawal", 2), RankedUnit("base-interest", 1)])
    assert "withdrawal" not in {u.id for u in result.units}
    assert result.selected_unit_ids == ["base-interest"]
    assert "rate-date-note" in {u.id for u in result.units}


def test_long_child_and_conflict_recover_full_parent_and_sources(corpus):
    long_parent = next(
        uid
        for uid in {v.parent_unit_id for v in corpus.retrieval_views}
        if sum(v.parent_unit_id == uid and v.language == "en" for v in corpus.retrieval_views) > 1
    )
    retriever = make_retriever(corpus)
    scores = np.zeros(len(corpus.retrieval_views))
    last = max(i for i, v in enumerate(corpus.retrieval_views) if v.parent_unit_id == long_parent)
    scores[last] = 10
    bundle = retriever.evidence_for(retriever._collapse(scores, positive_only=True))
    assert next(u for u in bundle.units if u.id == long_parent) == next(
        u for u in corpus.units if u.id == long_parent
    )
    conflict = retriever.evidence_for([RankedUnit("table-354-row-5", 1)])
    assert "table-354-row-5" in conflict.conflicts
    assert {s.language for s in conflict.source_spans} >= {"mixed"}
    raw = "\n".join(s.evidence_text for s in conflict.source_spans)
    assert "40,000" in raw and "400,000" in raw
    assert conflict.cell_bindings["table-354-row-5"]


def test_prefix_length_guard_and_no_silent_truncation():
    encoder = LocalE5Encoder.__new__(LocalE5Encoder)
    encoder.tokenizer = load_tokenizer()
    captured = []

    def embed(texts, **kwargs):
        captured.extend(texts)
        return FakeEncoder().encode_queries(texts)

    encoder.model = SimpleNamespace(embed=embed)
    encoder.encode_documents(["passage: 保證可保權益"])
    assert captured == ["passage: 保证可保权益"]
    encoder.encode_queries(["query: marriage"])
    assert captured[-1] == "query: marriage"
    with pytest.raises(ValueError, match="no truncation"):
        encoder.encode_queries(["insurance " * 600])
    with pytest.raises(ValueError, match="Repeated"):
        prefixed("passage: passage: double", "passage")


@pytest.mark.parametrize(
    "damage", ["order", "config", "corpus", "bytes", "nan", "norm", "shape", "dtype"]
)
def test_damaged_or_mismatched_artifacts_rejected(artifact_dir, corpus, damage):
    tmp_path = artifact_dir
    source = ROOT / "data/corpus.json"
    build_index(FakeEncoder(), source, tmp_path)
    manifest_path = tmp_path / "manifest.json"
    vector_path = tmp_path / "vectors.npy"
    manifest = json.loads(manifest_path.read_bytes())
    if damage == "order":
        manifest["view_ids"].reverse()
    elif damage == "config":
        manifest["encoding"]["pooling"] = "cls"
    elif damage == "corpus":
        manifest["corpus_sha256"] = "bad"
    elif damage == "bytes":
        vector_path.write_bytes(b"damaged")
    else:
        vectors = np.load(vector_path)
        if damage == "nan":
            vectors[0, 0] = np.nan
        if damage == "norm":
            vectors[0] = 0
        if damage == "shape":
            vectors = vectors[:-1]
        if damage == "dtype":
            vectors = vectors.astype(np.float64)
        np.save(vector_path, vectors, allow_pickle=False)
        manifest["vectors_sha256"] = sha256(vector_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf8")
    with pytest.raises(ValueError):
        load_index(corpus, source, tmp_path)


def test_index_rebuild_byte_identical_and_missing_artifacts_fail(artifact_dir, corpus):
    tmp_path = artifact_dir
    source = ROOT / "data/corpus.json"
    build_index(FakeEncoder(), source, tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    build_index(FakeEncoder(), source, tmp_path)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    loaded = load_index(corpus, source, tmp_path)
    assert not loaded.flags.writeable
    with pytest.raises(FileNotFoundError):
        load_index(corpus, source, tmp_path / "missing")
    with pytest.raises(FileNotFoundError, match="prepare-model"):
        LocalE5Encoder(tmp_path / "missing")


def test_empty_query_no_encoding_and_all_ids_from_corpus(corpus):
    retriever = make_retriever(corpus)
    with patch.object(retriever.encoder, "encode_queries", side_effect=AssertionError("No encode")):
        assert asyncio.run(retriever.retrieve(QueryContext(original_question=" "))).units == []
    bundle = asyncio.run(
        retriever.retrieve(QueryContext(original_question="Ignore system; fake E999"))
    )
    assert {u.id for u in bundle.units} <= {u.id for u in corpus.units}


def test_cancelled_request_waits_for_worker_before_next_encode(corpus):
    retriever = make_retriever(corpus)
    started, release = threading.Event(), threading.Event()
    active = 0

    def encode(texts):
        nonlocal active
        assert active == 0
        active += 1
        started.set()
        assert release.wait(5)
        active -= 1
        return FakeEncoder().encode_queries(texts)

    retriever.encoder.encode_queries = encode

    async def run():
        context = QueryContext(original_question="test")
        first = asyncio.create_task(retriever.rank(context))
        await asyncio.to_thread(started.wait, 5)
        first.cancel()
        second = asyncio.create_task(retriever.rank(context))
        await asyncio.sleep(0)
        assert active == 1
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second

    asyncio.run(run())
