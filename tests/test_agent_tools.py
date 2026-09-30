"""Read-only tool budgets and citation registration; no model API."""

import asyncio
import json
from unittest.mock import patch

import pytest

from insuretutor.agent_tools import EvidenceSearchSession, make_search_evidence_tool
from insuretutor.corpus import assemble_evidence
from insuretutor.retrieval.embedding import QueryInputError
from insuretutor.retrieval.index import load_corpus


class StubRetriever:
    def __init__(self):
        self.corpus = load_corpus()
        self.queries = []

    async def retrieve(self, context):
        self.queries.append(context.original_question)
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
        first = await session.search("withdraw")
        second = await session.search("currency")
        assert first.status == second.status == "evidence"
        assert first.evidence.selected_unit_ids == ["withdrawal"]
        assert second.evidence.selected_unit_ids == ["table-352-row-14"]
        assert {"note-6", "note-7", "cash-value-risk"} <= session.citable_units
        assert "table-352-row-14" in session.citable_units
        assert "table-352-row-15" not in session.citable_units
        assert len(session.bundles) == 2

    asyncio.run(run())


def test_limits_and_cache_do_not_reencode_or_repeat_source_cost():
    backend = StubRetriever()
    session = EvidenceSearchSession(backend, max_calls=2)

    async def run():
        first = await session.search("保證可保權益")
        second = await session.search("保证可保权益")
        assert first.remaining_source_characters == second.remaining_source_characters
        assert backend.queries == ["保证可保权益"]
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
        first = await session.search("conflict")
        assert first.status == "evidence" and first.evidence.conflicts
        assert first.remaining_source_characters == 0
        rejected = await session.search("withdraw")
        assert rejected.status == "evidence_budget" and rejected.evidence is None
        assert "withdrawal" not in session.citable_units
        assert session.bundles == [first.evidence]

    asyncio.run(run())


def test_empty_invalid_and_concurrent_calls_remain_bounded():
    session = EvidenceSearchSession(StubRetriever(), max_calls=2)

    async def run():
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
            assert (await session.search("oversized")).status == "invalid_query"
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
    tool = make_search_evidence_tool(session)
    assert tool.name == "search_evidence"
    assert set(tool.params_json_schema["properties"]) == {"query"}
    assert tool.params_json_schema["additionalProperties"] is False
    agents.Agent(name="Test", tools=[tool])

    async def run():
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

    asyncio.run(run())
