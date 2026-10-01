"""HTTP and reference adapters; no embedding weights or model API required."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from insuretutor.api import PDF, Runtime, create_app
from insuretutor.api import app as api_module
from insuretutor.chat_models import ChatResult, Citation, Claim
from insuretutor.corpus import Corpus, assemble_evidence
from insuretutor.references import with_references
from insuretutor.sessions import SessionCapacityError
from insuretutor.tutor import Tutor


@pytest.fixture(scope="module")
def corpus():
    return Corpus.model_validate_json(Path("data/corpus.json").read_bytes())


def result_for(corpus, uid="note-6", status="answered", language="zh-Hans"):
    bundle = assemble_evidence(corpus, [uid])
    spans = {s.id: s for s in bundle.source_spans}
    source_id = corpus.provenance["source"]["source_id"]
    citations = []
    for unit in bundle.units:
        for sid in unit.source_span_ids:
            span = spans[sid]
            if not unit.conflict and span.language != ("en" if language == "en" else "zh-Hant"):
                continue
            citations.append(
                Citation(
                    unit_ids=[unit.id],
                    span_id=sid,
                    quote=span.evidence_text,
                    pdf_page=span.pdf_page,
                    language=span.language,
                    source_id=source_id,
                    source_url=f"/sources/{source_id}.pdf#page={span.pdf_page}",
                    bbox_raw=span.bbox_raw,
                    text_origin=span.text_origin,
                )
            )
    return ChatResult(
        session_id="test-session",
        response_language=language,
        status=status,
        explanation="Validated explanation",
        citations=citations,
        claims=[Claim(text="Validated fact", evidence_ids=[uid])]
        if status not in {"excerpts", "insufficient", "refused"}
        else [],
        clarification_question="Which condition applies?" if status == "clarification" else None,
        reason="timeout" if status == "excerpts" else None,
    )


class StubTutor:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.turns = []

    async def answer(self, turn):
        self.turns.append(turn)
        if self.error:
            raise self.error
        return self.result


def client_for(corpus, tutor):
    return TestClient(
        create_app(lambda: Runtime(tutor, corpus, PDF)), raise_server_exceptions=False
    )


@pytest.mark.parametrize(
    "status",
    [
        "answered",
        "clarification",
        "refused",
        "insufficient",
        "source_conflict",
        "excerpts",
    ],
)
def test_chat_statuses_and_session_pass_through(corpus, status):
    tutor = StubTutor(result_for(corpus, status=status))
    with client_for(corpus, tutor) as client:
        response = client.post(
            "/api/chat",
            json={
                "question": "保单条件？",
                "session_id": "previous-session",
                "response_language": "zh-Hant",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == status and body["session_id"] == "test-session"
        assert tutor.turns[0].session_id == "previous-session"
        assert tutor.turns[0].response_language == "zh-Hant"
        assert body["reference_groups"][0]["unit_id"] == "note-6"
        assert {v["language"] for v in body["reference_groups"][0]["versions"]} == {"en", "zh-Hant"}
        assert response.headers["X-Request-ID"]
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": " "},
        {"question": "x" * 4001},
        {"question": "a", "response_language": "fr"},
        {"question": "a", "system": "SECRET"},
    ],
)
def test_invalid_requests_do_not_echo_payload(corpus, payload):
    tutor = StubTutor(result_for(corpus))
    with client_for(corpus, tutor) as client:
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_input"
        assert "SECRET" not in response.text
        assert not tutor.turns


@pytest.mark.parametrize(
    "error,status,code",
    [
        (SessionCapacityError("SECRET"), 503, "sessions_busy"),
        (RuntimeError("SECRET"), 500, "internal_error"),
    ],
)
def test_errors_are_redacted(corpus, error, status, code, caplog):
    with client_for(corpus, StubTutor(error=error)) as client:
        response = client.post("/api/chat", json={"question": "PRIVATE QUESTION"})
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert "SECRET" not in response.text + caplog.text
        assert "PRIVATE QUESTION" not in caplog.text
        assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_health_assets_and_pdf_range(corpus):
    tutor = StubTutor(result_for(corpus))
    with client_for(corpus, tutor) as client:
        health = client.get("/api/health").json()
        assert health["ready"] and health["mode"] == "excerpts" and not tutor.turns
        page = client.get("/")
        assert page.status_code == 200
        assert page.headers["Cache-Control"] == "no-cache"
        for asset in [
            "app.js",
            "styles.css",
            "pdf-viewer.js",
            "vendor/pdf.min.mjs",
            "vendor/pdf.worker.min.mjs",
        ]:
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "no-cache"
            assert client.get(
                f"/static/{asset}", headers={"If-None-Match": response.headers["ETag"]}
            ).headers["Cache-Control"] == "no-cache"
        response = client.get(health["pdf_url"], headers={"Range": "bytes=0-4"})
        assert response.status_code == 206 and response.content == b"%PDF-"
        assert (
            client.get(health["pdf_url"], headers={"Range": "bytes=999999999-"}).status_code == 416
        )
        for path in ["/.env", "/sources/unknown.pdf", "/static/../../.env", "/static/demo.json"]:
            assert client.get(path).status_code == 404


def test_reference_groups_recover_required_notes_and_originals(corpus):
    result = result_for(corpus, "withdrawal", language="en")
    groups = with_references(result, corpus).reference_groups
    main = next(g for g in groups if g.unit_id == "withdrawal")
    assert "note-6" in main.required_unit_ids
    assert set(main.required_unit_ids) <= {g.unit_id for g in groups}
    spans = {s.id: s for s in corpus.source_spans}
    for group in groups:
        for version in group.versions:
            for source in version.sources:
                assert source.quote == spans[source.span_id].evidence_text
                assert source.pdf_page == spans[source.span_id].pdf_page
                assert source.bbox_raw == spans[source.span_id].bbox_raw
                assert source.language == version.language


def test_conflict_both_versions_and_whole_table_precision(corpus):
    response = with_references(result_for(corpus, "table-354-row-5"), corpus)
    group = next(g for g in response.reference_groups if g.unit_id == "table-354-row-5")
    assert group.conflict
    assert {v.language for v in group.versions} == {"en", "zh-Hant"}
    assert all(
        s.bbox_precision == "whole_table"
        for v in group.versions
        for s in v.sources
        if s.role == "body"
    )


def test_unknown_or_unbacked_claim_is_rejected(corpus):
    result = result_for(corpus)
    result.claims[0].evidence_ids = ["invented"]
    with pytest.raises(ValueError):
        with_references(result, corpus)
    result = result_for(corpus)
    result.citations[0].quote = "invented quote"
    with pytest.raises(ValueError):
        with_references(result, corpus)


def test_http_real_tutor_new_session_and_expiration(corpus):
    class Retriever:
        async def retrieve(self, _context):
            return assemble_evidence(corpus, ["note-6"])

    tutor = Tutor(Retriever())
    with client_for(corpus, tutor) as client:
        first = client.post("/api/chat", json={"question": "提款条件？"}).json()
        second = client.post(
            "/api/chat", json={"question": "Withdrawal?", "session_id": first["session_id"]}
        ).json()
        assert first["session_id"] == second["session_id"]
        assert second["response_language"] == "en"
        tutor.sessions.sessions.clear()
        expired = client.post(
            "/api/chat", json={"question": "提款条件？", "session_id": first["session_id"]}
        ).json()
        assert expired["context_reset"] and expired["session_id"] != first["session_id"]


def test_startup_rejects_wrong_pdf(corpus, monkeypatch):
    monkeypatch.setattr(api_module, "sha256", lambda _path: "wrong-pdf-hash")
    monkeypatch.setattr(
        api_module.HybridRetriever, "from_local", lambda: SimpleNamespace(corpus=corpus)
    )
    with pytest.raises(ValueError, match="PDF hash"):
        api_module.load_runtime()


def test_generator_lifecycle_and_health_does_not_call_provider(corpus):
    class Generator:
        closed = False

        async def close(self):
            self.closed = True

    generator = Generator()
    runtime = Runtime(StubTutor(result_for(corpus)), corpus, PDF, generator)
    with TestClient(create_app(lambda: runtime)) as client:
        assert client.get("/api/health").json()["mode"] == "agent"
        assert not runtime.tutor.turns and not generator.closed
    assert generator.closed
