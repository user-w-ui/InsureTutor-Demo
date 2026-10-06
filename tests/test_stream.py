"""SSE progress stream over the real Tutor and SDK Runner with scripted models."""

import asyncio
import json
import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from insuretutor.agent_tools import EvidenceSearchSession
from insuretutor.api import PDF, Runtime, create_app
from insuretutor.api.app import chat_events
from insuretutor.chat_models import ChatTurn
from insuretutor.corpus import Corpus
from insuretutor.generation import POLICY, AgentGenerator
from insuretutor.references import display_title
from insuretutor.sessions import SessionCapacityError
from insuretutor.tutor import Tutor
from tests.test_chat import FakeRetriever, ScriptModel, draft

SUPPLEMENT = [
    [("search_evidence", "Guaranteed Insurability Option limits")],
    json.dumps(
        {
            "status": "answered",
            "claims": [
                {"text": "Periodic withdrawal requires 10 years.", "evidence_ids": ["note-6"]},
                {"text": "The option can be exercised twice.", "evidence_ids": ["note-3"]},
            ],
        }
    ),
]


@pytest.fixture(scope="module")
def corpus():
    return Corpus.model_validate_json(Path("data/corpus.json").read_text(encoding="utf-8"))


def parse(text):
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events


def tutor_for(corpus, actions=None, groups=None, **kwargs):
    generator = AgentGenerator(ScriptModel(actions)) if actions else None
    return Tutor(FakeRetriever(corpus, groups), generator, **kwargs)


def client_for(corpus, tutor):
    return TestClient(
        create_app(lambda: Runtime(tutor, corpus, PDF)), raise_server_exceptions=False
    )


def stream(corpus, tutor, question="When can I withdraw?"):
    with client_for(corpus, tutor) as client:
        response = client.post("/api/chat/stream", json={"question": question})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    return parse(response.text), response.text


def labels(events):
    return [(name, data.get("stage") or data.get("kind")) for name, data in events]


def test_event_order_and_final_matches_non_stream_response(corpus):
    groups = [["withdrawal"], ["insurability"]]
    events, text = stream(corpus, tutor_for(corpus, SUPPLEMENT, groups))
    assert labels(events) == [
        ("stage", "retrieving"),
        ("search", "initial"),
        ("stage", "thinking"),
        ("stage", "searching"),
        ("search", "supplement"),
        ("stage", "thinking"),
        ("stage", "validating"),
        ("final", None),
    ]
    elapsed = [data["elapsed_ms"] for _, data in events]
    assert elapsed == sorted(elapsed)
    assert [d["model_call"] for _, d in events if d.get("stage") == "thinking"] == [1, 2]

    initial, supplement = (d for name, d in events if name == "search")
    assert "query" not in initial and initial["remaining_searches"] == 5
    assert supplement["query"] == "Guaranteed Insurability Option limits"
    assert supplement["status"] == "evidence" and supplement["remaining_searches"] == 4
    units = {u.id: u for u in corpus.units}
    spans = {s.id: s for s in corpus.source_spans}
    for hit in supplement["hits"]:
        record = next(r for r in units[hit["unit_id"]].segments if r.language == "en")
        # Same label as the reference links, in the answer's citation language.
        assert hit["title"] == display_title(hit["unit_id"], record, spans) and hit["pages"]
    assert supplement["required_added"] >= 0

    with client_for(corpus, tutor_for(corpus, SUPPLEMENT, groups)) as client:
        expected = client.post("/api/chat", json={"question": "When can I withdraw?"}).json()
    final = events[-1][1]["response"]
    assert final["status"] == "answered"
    assert {**final, "session_id": None} == {**expected, "session_id": None}

    # Progress carries short labels and pages, never source bodies, prompts or keys.
    progress = text.split("event: final")[0]
    for uid in ["withdrawal", "insurability", "note-6", "note-3"]:
        for sid in units[uid].source_span_ids:
            if len(spans[sid].evidence_text) > 80:
                assert spans[sid].evidence_text not in progress
    assert POLICY[:80] not in progress and "LLM_API_KEY" not in progress


def test_fallback_paths_still_emit_final(corpus):
    events, _ = stream(corpus, tutor_for(corpus))
    assert labels(events) == [
        ("stage", "retrieving"),
        ("search", "initial"),
        ("stage", "fallback"),
        ("final", None),
    ]
    assert events[2][1]["reason"] == "model_unconfigured"
    assert events[-1][1]["response"]["status"] == "excerpts"

    events, _ = stream(corpus, tutor_for(corpus, ["not json"]))
    assert labels(events)[2:] == [
        ("stage", "thinking"),
        ("stage", "validating"),
        ("stage", "repairing"),
        ("stage", "validating"),
        ("stage", "fallback"),
        ("final", None),
    ]
    assert events[-2][1]["reason"] == "invalid_json"
    final = events[-1][1]["response"]
    assert final["status"] == "excerpts" and final["reason"] == "invalid_json"
    assert final["model_calls"] == 2


def test_timeout_emits_fallback_then_final(corpus):
    async def slow():
        await asyncio.sleep(1)
        return draft()

    events, _ = stream(corpus, tutor_for(corpus, [slow], timeout=0.05))
    assert labels(events)[-2:] == [("stage", "fallback"), ("final", None)]
    assert events[-2][1]["reason"] == "timeout"
    assert events[-1][1]["response"]["reason"] == "timeout"


class FailingTutor:
    def __init__(self, error):
        self.error = error

    async def answer(self, turn, progress=None):
        raise self.error


@pytest.mark.parametrize(
    "error,code",
    [(SessionCapacityError("SECRET"), "sessions_busy"), (RuntimeError("SECRET"), "internal_error")],
)
def test_stream_errors_are_redacted(corpus, error, code, caplog):
    caplog.set_level(logging.INFO, logger="insuretutor.api")
    events, text = stream(corpus, FailingTutor(error), question="PRIVATE QUESTION")
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["code"] == code and events[0][1]["request_id"]
    assert f"request={events[0][1]['request_id']}" in caplog.text
    assert "SECRET" not in text + caplog.text
    assert "PRIVATE QUESTION" not in caplog.text


def test_invalid_stream_input_is_rejected_before_streaming(corpus):
    tutor = FailingTutor(AssertionError("must not run"))
    with client_for(corpus, tutor) as client:
        response = client.post("/api/chat/stream", json={"question": " ", "system": "SECRET"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert "SECRET" not in response.text


@pytest.mark.asyncio
async def test_disconnect_detaches_turn_which_completes_and_releases_session(corpus):
    async def slow():
        await asyncio.sleep(0.1)
        return draft()

    tutor = tutor_for(corpus, [slow])
    runtime, tasks = Runtime(tutor, corpus, PDF), set()
    events = chat_events(
        runtime, ChatTurn(question="When can I withdraw?"), "rid", time.perf_counter(), tasks
    )
    first = await anext(events)
    assert first.event == "stage" and first.data["stage"] == "retrieving"
    await events.aclose()  # The client went away mid-turn.
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    assert not tasks
    (session,) = tutor.sessions.sessions.values()
    assert len(session.history) == 1 and not session.lock.locked()


@pytest.mark.asyncio
async def test_progress_failures_never_change_answer_and_queries_are_bounded(corpus):
    def broken(_event):
        raise RuntimeError("display failed")

    tutor = tutor_for(corpus, SUPPLEMENT, [["withdrawal"], ["insurability"]])
    result = await tutor.answer(ChatTurn(question="When can I withdraw?"), progress=broken)
    assert result.status == "answered" and result.searches == 2

    seen = []
    search = EvidenceSearchSession(
        FakeRetriever(corpus), response_language="zh-Hans", max_calls=2, on_search=seen.append
    )
    await search.initialize("提款条件？")
    await search.search("x" * 300)
    await search.search("limit")
    assert [e.kind for e in seen] == ["initial", "supplement", "supplement"]
    assert seen[0].query is None and len(seen[1].query) == 200
    assert seen[2].status == "search_limit" and not seen[2].hits
    # Chinese answers keep the original Traditional Chinese labels, like citations.
    units = {u.id: u for u in corpus.units}
    spans = {s.id: s for s in corpus.source_spans}
    hit = seen[0].hits[0]
    record = next(r for r in units[hit.unit_id].segments if r.language == "zh-Hant")
    assert hit.title == display_title(hit.unit_id, record, spans)
