"""Read-only tool budgets and citation registration; no model API."""

import asyncio
import json
from unittest.mock import patch

import pytest

from insuretutor.agent_tools import EvidenceSearchSession, SearchResult, make_search_evidence_tool
from insuretutor.corpus import assemble_evidence
from insuretutor.retrieval.embedding import QueryInputError
from insuretutor.retrieval.index import load_corpus


class StubRetriever:
    def __init__(self):
        self.corpus = load_corpus()
        self.queries = []
        self.contexts = []

    async def retrieve(self, context):
        self.queries.append(context.original_question)
        self.contexts.append(context)
        unit = {
            "withdraw": "withdrawal",
            "currency": "table-352-row-14",
            "conflict": "table-354-row-5",
            "empty": None,
        }.get(context.original_question, "note-3")
        return assemble_evidence(self.corpus, [unit] if unit else [])


def test_separate_calls_keep_full_bundles_and_allow_only_seen_citations():
    session = EvidenceSearchSession(StubRetriever())

    async def run():
        first = await session.initialize("withdraw")
        second = await session.search("currency")
        assert first.status == second.status == "evidence"
        assert first.evidence.selected_unit_ids == ["withdrawal"]
        assert second.evidence.selected_unit_ids == ["table-352-row-14"]
        assert {"note-6", "note-7", "cash-value-risk"} <= session.citable_units
        assert "table-352-row-14" in session.citable_units
        assert "table-352-row-15" not in session.citable_units
        assert len(session.bundles) == 2
        assert first.remaining_searches == 5 and second.remaining_searches == 4

    asyncio.run(run())


def test_limits_and_cache_do_not_reencode_or_repeat_source_cost():
    backend = StubRetriever()
    session = EvidenceSearchSession(backend, max_calls=2)

    async def run():
        first = await session.initialize("保證可保權益")
        second = await session.search("保证可保权益")
        assert first.remaining_source_characters == second.remaining_source_characters
        # Same normalized text, different expansion mode: two distinct retrievals.
        # The source is charged once because the second bundle repeats the first.
        assert backend.queries == ["保證可保權益", "保证可保权益"]
        assert len(session.bundles) == 2
        # Both came back, but the repeated source is charged once: the second
        # bundle contributes a different note under the same origin.
        assert session.source_characters
        assert first.remaining_source_characters == second.remaining_source_characters
        third = await session.search("currency")
        assert third.status == "search_limit" and third.evidence is None
        assert third.remaining_searches == 0

    asyncio.run(run())


def test_budget_rejects_whole_bundle_without_registering_citations():
    backend = StubRetriever()
    minimal = assemble_evidence(backend.corpus, ["table-354-row-5"])
    session = EvidenceSearchSession(
        backend, character_budget=sum(len(s.evidence_text) for s in minimal.source_spans)
    )

    async def run():
        first = await session.initialize("conflict")
        assert first.status == "evidence" and first.evidence.conflicts
        injected = json.loads(first.to_agent_json())
        assert injected["evidence"]["conflicts"]
        assert injected["evidence"]["source_spans"][0]["pdf_page"] == 17
        assert all("text" not in u for u in injected["evidence"]["units"])
        assert first.remaining_source_characters == 0
        rejected = await session.search("withdraw")
        assert rejected.status == "evidence_budget" and rejected.evidence is None
        assert "withdrawal" not in session.citable_units
        assert session.bundles == [first.evidence]

    asyncio.run(run())


def test_empty_invalid_and_concurrent_calls_remain_bounded():
    session = EvidenceSearchSession(StubRetriever(), max_calls=3)

    async def run():
        assert (await session.initialize("empty")).status == "no_evidence"
        results = await asyncio.gather(
            session.search(""), session.search("empty"), session.search("withdraw")
        )
        assert [r.status for r in results] == ["invalid_query", "no_evidence", "search_limit"]
        assert not session.citable_units and not session.bundles

    asyncio.run(run())


def test_recoverable_input_error_is_distinct_from_backend_failure():
    backend = StubRetriever()
    session = EvidenceSearchSession(backend)

    async def run():
        with patch.object(backend, "retrieve", side_effect=QueryInputError("Too long")):
            assert (await session.initialize("oversized")).status == "invalid_query"
        with (
            patch.object(backend, "retrieve", side_effect=ValueError("Bad vectors")),
            pytest.raises(ValueError, match="Bad vectors"),
        ):
            await session.search("valid")
        assert not session.citable_units

    asyncio.run(run())


def test_sdk_schema_and_actual_invocation_without_network():
    agents = pytest.importorskip("agents", reason="Optional SDK adapter requires .[agent]")
    from agents.tool_context import ToolContext

    session = EvidenceSearchSession(StubRetriever())

    async def run():
        await session.initialize("withdraw")
        tool = make_search_evidence_tool(session)
        assert tool.name == "search_evidence"
        assert set(tool.params_json_schema["properties"]) == {"query"}
        assert tool.params_json_schema["additionalProperties"] is False
        agents.Agent(name="Test", tools=[tool])
        arguments = json.dumps({"query": "conflict"})
        ctx = ToolContext(
            context=None, tool_name=tool.name, tool_call_id="call-test", tool_arguments=arguments
        )
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            output = await tool.on_invoke_tool(ctx, arguments)
        result = json.loads(output)
        assert result["evidence"]["conflicts"]
        assert result["evidence"]["source_spans"][0]["pdf_page"] == 17
        assert "bbox_raw" in result["evidence"]["source_spans"][0]
        assert "text_origin" in result["evidence"]["source_spans"][0]
        assert all("text" not in u for u in result["evidence"]["units"])
        assert "table-354-row-5" in session.citable_units
        assert "withdrawal" in session.citable_units

    asyncio.run(run())


def test_initial_retrieval_is_once_unsplit_and_citable_without_tool_calls():
    backend = StubRetriever()
    session = EvidenceSearchSession(backend, response_language="en")
    raw_question = " 保證可保權益有哪些條件？ What are the withdrawal limits? "

    async def run():
        with pytest.raises(RuntimeError, match="Initialize"):
            await session.search("withdraw")
        with pytest.raises(RuntimeError, match="Initialize"):
            make_search_evidence_tool(session)
        first = await session.initialize(raw_question)
        assert backend.queries == [raw_question]
        assert backend.contexts[0].rewritten_query is None
        assert backend.contexts[0].response_language == "en"
        assert first.remaining_searches == 5 and session.calls == 1
        assert session.citable_units == {u.id for u in first.evidence.units}
        with pytest.raises(RuntimeError, match="already attempted"):
            await session.initialize("currency")
        assert backend.queries == [raw_question] and session.calls == 1

    asyncio.run(run())


def test_empty_initial_result_still_allows_supplemental_evidence():
    session = EvidenceSearchSession(StubRetriever())

    async def run():
        first = await session.initialize("empty")
        assert first.status == "no_evidence" and not session.citable_units
        assert "evidence" not in json.loads(first.to_agent_json())
        second = await session.search("withdraw")
        assert second.status == "evidence" and "note-6" in session.citable_units

    asyncio.run(run())


def test_initial_backend_failure_does_not_enable_agent_tool():
    backend = StubRetriever()
    session = EvidenceSearchSession(backend)

    async def run():
        with (
            patch.object(backend, "retrieve", side_effect=ValueError("Bad vectors")),
            pytest.raises(ValueError, match="Bad vectors"),
        ):
            await session.initialize("withdraw")
        assert session.initial_result is None and not session.citable_units
        with pytest.raises(RuntimeError, match="Initialize"):
            make_search_evidence_tool(session)
        with pytest.raises(RuntimeError, match="already attempted"):
            await session.initialize("withdraw")

    asyncio.run(run())


@pytest.mark.parametrize(
    "question",
    ["What are the conditions?", "條件是甚麼？", "條件是甚麼？ What are the conditions?"],
)
def test_initial_and_supplemental_results_keep_both_languages(question):
    session = EvidenceSearchSession(StubRetriever(), response_language="en")

    async def run():
        initial = await session.initialize(question)
        supplement = await session.search("currency")
        for result in [initial, supplement]:
            payload = json.loads(result.to_agent_json())["evidence"]
            assert {s["language"] for s in payload["source_spans"]} == {"en", "zh-Hant"}
            for unit in payload["units"]:
                assert {r["language"] for r in unit["segments"]} == {"en", "zh-Hant"}
                assert all(r["pair_id"] == unit["id"] for r in unit["segments"])

    asyncio.run(run())


def test_serialized_corpus_keeps_language_links_and_split_source_provenance():
    corpus = load_corpus()
    bundle = assemble_evidence(corpus, [u.id for u in corpus.units])
    result = SearchResult(
        status="evidence", evidence=bundle, remaining_searches=5, remaining_source_characters=0
    )
    payload = json.loads(result.to_agent_json())["evidence"]
    sources = {s["id"]: s for s in payload["source_spans"]}
    originals = {s.id: s for s in bundle.source_spans}
    assert len(sources) == len(payload["source_spans"]) == len(originals)
    assert {u["id"] for u in payload["units"]} == {u.id for u in corpus.units}
    assert all("text" not in u for u in payload["units"])
    for unit in payload["units"]:
        peers = {r["id"]: r for r in unit["segments"]}
        for record in peers.values():
            assert peers[record["parallel_id"]]["parallel_id"] == record["id"]
            assert all(
                sources[sid]["language"] == record["language"]
                for sid in record["source_span_ids"] + record["context_span_ids"]
            )
        for sid in payload["context_by_unit"][unit["id"]]:
            assert sid in sources
        for binding in payload["cell_bindings"][unit["id"]]:
            assert binding["cell"] in sources
            assert all(sid in sources for sid in binding["column_headers"])
    for sid, span in sources.items():
        expected = originals[sid]
        assert span["evidence_text"] == expected.evidence_text
        assert span["pdf_page"] == expected.pdf_page
        assert span["bbox_raw"] == expected.bbox_raw
        assert span["origin_span_id"] == expected.origin_span_id
        assert span["origin_ranges"] == expected.origin_ranges
    conflict = next(u for u in payload["units"] if u["id"] == "table-354-row-5")
    assert conflict["pairing_status"] == "reviewed_source_conflict"
    assert conflict["id"] in payload["conflicts"]
    assert any(s.get("bbox_precision") == "whole_table" for s in sources.values())


def test_shared_origin_does_not_merge_languages_or_undercharge_source_budget():
    backend = StubRetriever()
    bundle = assemble_evidence(backend.corpus, ["table-354-row-5"])
    cost = sum(len(s.evidence_text) for s in bundle.source_spans)
    session = EvidenceSearchSession(backend, character_budget=cost)

    async def run():
        first = await session.initialize("conflict")
        origins = {}
        for span in first.evidence.source_spans:
            origins.setdefault(span.origin_span_id, []).append(span)
        paired = [spans for spans in origins.values() if len(spans) == 2]
        assert paired
        for spans in paired:
            assert {s.language for s in spans} == {"en", "zh-Hant"}
            assert len({s.id for s in spans}) == 2
            assert all(s.id in session.source_characters for s in spans)
        assert sum(session.source_characters.values()) == cost
        assert first.remaining_source_characters == 0
        assert (await session.search("conflict")).remaining_source_characters == 0
        assert backend.queries == ["conflict", "conflict"]

    asyncio.run(run())


def test_only_the_initial_search_expands_sentences():
    """The opening turn may split a multi-sentence question; tool calls may not."""
    retriever = StubRetriever()
    session = EvidenceSearchSession(retriever)

    async def run():
        await session.initialize("first sentence? second sentence?")
        await session.search("agent supplied query? still one query?")

    asyncio.run(run())
    assert [c.expand_sentences for c in retriever.contexts] == [True, False]
    # The verbatim queries reach the retriever unchanged on both paths.
    assert retriever.queries == [
        "first sentence? second sentence?",
        "agent supplied query? still one query?",
    ]


def test_cache_does_not_leak_across_expansion_modes():
    retriever = StubRetriever()
    session = EvidenceSearchSession(retriever)
    question = "withdraw"

    async def run():
        first = await session.initialize(question)
        # Resubmitting the opening text must retrieve it verbatim, not replay the
        # expanded bundle stored under the same normalized text.
        again = await session.search(question)
        assert first.status == again.status == "evidence"

    asyncio.run(run())
    assert [c.expand_sentences for c in retriever.contexts] == [True, False]
