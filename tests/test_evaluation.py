"""Offline evaluation metrics; no model API, judge or embedding weights required."""

import csv
import json
from pathlib import Path

import pytest

from insuretutor.chat_models import Calculation, CalculationInput, ChatResult, Citation, Claim
from insuretutor.corpus import Corpus, assemble_evidence
from insuretutor.evaluation import (
    JudgeError,
    answer_view,
    citation_precision,
    citation_recall,
    judge_tasks,
    judged_scores,
    load_items,
    percentile,
    rubric_result,
    score,
    status_correct,
    summarize,
)


@pytest.fixture(scope="module")
def corpus():
    return Corpus.model_validate_json(Path("data/corpus.json").read_bytes())


@pytest.fixture(scope="module")
def items():
    return {i["id"].split("-")[0]: i for i in load_items()}


def cite(uid, page=1, language="en", quote="SOURCE BODY"):
    return Citation(
        unit_ids=[uid],
        span_id=f"span-{uid}",
        quote=quote,
        pdf_page=page,
        language=language,
        source_id="src",
        source_url=f"/sources/src.pdf#page={page}",
        bbox_raw=[],
        text_origin="mineru",
    )


def result(status="answered", claims=(), citations=(), reason=None, **kwargs):
    return ChatResult(
        session_id="s",
        response_language="zh-Hans",
        status=status,
        explanation="text",
        claims=list(claims),
        citations=list(citations),
        reason=reason,
        **kwargs,
    )


BOUNDARY = Claim(kind="boundary", text="scope", boundary="scope")


def test_status_rules_follow_item_fields_and_fail_fallbacks(items):
    assert status_correct(items["q1"], result("answered"))
    assert not status_correct(items["q1"], result("clarification"))
    # q8 is told to clarify a vague education request first.
    assert status_correct(items["q8"], result("clarification"))
    assert status_correct(items["q2"], result("source_conflict"))
    assert not status_correct(items["q2"], result("answered"))
    # A refusal may answer around an explicit boundary, but not answer outright.
    assert status_correct(items["q9"], result("refused"))
    assert status_correct(items["q9"], result("answered", [BOUNDARY]))
    assert status_correct(items["q9"], result("clarification", [BOUNDARY]))
    assert not status_correct(items["q9"], result("answered", [Claim(text="fact")]))
    # Any degraded or failed turn is wrong, whatever its status.
    assert not status_correct(items["q9"], result("insufficient", reason="no_evidence"))
    assert not status_correct(items["q1"], result("excerpts", reason="timeout"))


def test_recall_counts_server_closure_units_and_skips_refusals(items):
    item = items["q5"]
    expected = sorted(e["unit_id"] for e in item["evidence"]["required"])
    assert len(expected) == 2
    # The server added the second unit by closure; it still counts as shown.
    shown = result(claims=[Claim(text="a", evidence_ids=[expected[0]])])
    shown.citations = [cite(expected[0]), cite(expected[1])]
    assert citation_recall(item, shown) == 1
    assert citation_recall(item, result(citations=[cite(expected[0])])) == 0.5
    assert citation_recall(items["q9"], result("refused")) is None


def test_precision_uses_closure_and_counts_formula_references(items, corpus):
    item = items["q5"]
    listed = {e["unit_id"] for role in ("required", "supporting") for e in item["evidence"][role]}
    closure = {u.id for u in assemble_evidence(corpus, sorted(listed)).units}
    implied = sorted(closure - listed)
    assert implied, "a note implied by the listed units"
    claims = [
        Claim(text="a", evidence_ids=[implied[0]]),
        Claim(text="b", evidence_ids=["guarantee-summary"]),
    ]
    assert citation_precision(item, result(claims=claims), corpus) == 0.5
    # A formula reference is a model-selected unit like any evidence ID.
    item = items["q4"]
    calculation = Calculation(
        formula_id="table-97-row-3",
        formula_expression="x",
        inputs=[
            CalculationInput(name="basic_sum_insured", user_text="a"),
            CalculationInput(name="account_value", user_text="b"),
        ],
        steps="s",
        result="r",
    )
    formula = Claim(kind="calculation", text="c", calculation=calculation)
    assert citation_precision(item, result(claims=[formula]), corpus) == 1
    # A supporting unit (note 4, cited for contrast) is relevant but not required.
    contrast = Claim(text="c", evidence_ids=["note-4"])
    assert citation_precision(item, result(claims=[contrast]), corpus) == 1
    other = calculation.model_copy(update={"formula_id": "table-97-row-1"})
    wrong = Claim(kind="calculation", text="c", calculation=other)
    assert citation_precision(item, result(claims=[wrong]), corpus) == 0
    # Nothing selected by the model: not applicable, rather than perfect or zero.
    assert citation_precision(item, result(claims=[BOUNDARY]), corpus) is None
    grounding = sorted(e["unit_id"] for e in items["q10"]["evidence"]["supporting"])
    refusal = result("refused", [Claim(text="basis", evidence_ids=grounding[:1])])
    assert citation_precision(items["q10"], refusal, corpus) == 1


def judged(item, scores):
    return {
        "item_id": item["id"],
        "round": 1,
        "scores": [{"line": n, "score": s, "reason": "r"} for n, s in enumerate(scores, 1)],
    }


def test_rubric_veto_bonus_and_partial_scores(items):
    q1 = items["q1"]  # Six lines; line 4 is bonus.
    scores = judged_scores(q1, judged(q1, [1, 1, 0.5, 0, 1, 1]))
    outcome = rubric_result(q1, scores)
    assert outcome["rubric_score"] == pytest.approx(4.5 / 5)
    assert outcome["bonus_score"] == 0 and not outcome["full_score"]
    assert rubric_result(q1, judged_scores(q1, judged(q1, [1, 1, 1, 0, 1, 1])))["full_score"]

    q8 = items["q8"]  # Line 1 is the veto line.
    outcome = rubric_result(q8, judged_scores(q8, judged(q8, [0, 1, 1])))
    assert outcome == {
        "rubric_score": 0.0,
        "full_score": False,
        "veto_failed": True,
        "bonus_score": None,
    }


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda j: j["scores"].pop(), "scored 2 of 3"),
        (lambda j: j["scores"].append(dict(j["scores"][0])), "repeated line"),
        (lambda j: j["scores"][0].update(score=0.7), "invalid score"),
        (lambda j: j["scores"][0].update(score=0.5), "invalid score"),  # Veto line.
        (lambda j: j.update(item_id="q1-other"), "item_id"),
    ],
)
def test_incomplete_or_invalid_judge_output_is_rejected(items, mutate, message):
    output = judged(items["q8"], [1] * 3)
    mutate(output)
    with pytest.raises(JudgeError, match=message):
        judged_scores(items["q8"], output)


def test_summary_averages_items_first_and_ignores_not_applicable():
    def row(item_id, rubric, recall, elapsed):
        return {
            "item_id": item_id,
            "status_correct": True,
            "citation_recall": recall,
            "citation_precision": None,
            "rubric_score": rubric,
            "full_score": rubric == 1,
            "bonus_score": None,
            "elapsed_ms": elapsed,
            "searches": 2,
            "model_calls": 2,
            "repairs": 0,
            "reason": None,
        }

    rows = [row("a", 1, 1, 1000), row("a", 0, 0.5, 2000), row("b", 1, None, 9000)]
    summary = summarize(rows)
    assert summary["per_item"]["a"]["rubric_score"] == 0.5
    assert summary["per_item"]["a"]["full_scores"] == 1
    assert summary["per_item"]["b"]["citation_recall"] is None
    # Macro over items: (0.5 + 1) / 2, not over the three runs.
    assert summary["overall"]["rubric_score"] == 0.75
    assert summary["overall"]["citation_recall"] == 0.75
    assert summary["overall"]["citation_precision"] is None
    assert summary["overhead"]["p95_s"] == 9 and summary["overhead"]["p50_s"] == 2
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3


def test_answer_view_carries_anchors_not_source_text(items):
    view = answer_view(
        items["q5"],
        2,
        result(
            claims=[Claim(text="answer", evidence_ids=["note-6"])],
            citations=[cite("note-6", 12), cite("note-6", 13, "zh-Hant")],
        ),
    )
    assert view["round"] == 2 and view["claims"][0]["evidence_ids"] == ["note-6"]
    assert view["cited_units"] == [
        {"unit_id": "note-6", "pdf_pages": [12, 13], "languages": ["en", "zh-Hant"]}
    ]
    assert "SOURCE BODY" not in json.dumps(view)


def test_judge_tasks_and_score_end_to_end(items, tmp_path):
    item = items["q9"]
    (tmp_path / "items").mkdir()
    (tmp_path / "answers").mkdir()
    (tmp_path / "judge").mkdir()
    (tmp_path / "items" / f"{item['id']}.json").write_text(json.dumps(item), encoding="utf-8")
    records = []
    for round_number in (1, 2):
        answer = result("refused", [BOUNDARY])
        name = f"r{round_number}-{item['id']}.json"
        view = answer_view(item, round_number, answer)
        (tmp_path / "answers" / name).write_text(json.dumps(view), encoding="utf-8")
        records.append(
            {
                "round": round_number,
                "item_id": item["id"],
                "elapsed_ms": 1000 * round_number,
                "events": [{"event": "stage", "stage": "repairing"}] * (round_number - 1),
                "result": answer.model_dump(mode="json"),
            }
        )
    (tmp_path / "raw.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    tasks = judge_tasks(tmp_path)
    assert [t["name"] for t in tasks] == [f"r1-{item['id']}", f"r2-{item['id']}"]
    for placeholder in ("{item_path}", "{answer_path}", "{output_path}"):
        assert placeholder not in tasks[0]["prompt"]
    assert f"r1-{item['id']}.json" in tasks[0]["prompt"]
    assert "expected_answer" in tasks[0]["prompt"]  # The fixed template itself.

    (tmp_path / "judge" / f"r1-{item['id']}.json").write_text(
        json.dumps(judged(item, [1] * 5)), encoding="utf-8"
    )
    assert [t["name"] for t in judge_tasks(tmp_path)] == [f"r2-{item['id']}"]
    with pytest.raises(JudgeError, match=f"r2-{item['id']}"):
        score(tmp_path)
    (tmp_path / "judge" / f"r2-{item['id']}.json").write_text(
        json.dumps(judged(item, [0, 1, 1, 1, 1])), encoding="utf-8"
    )
    summary = score(tmp_path)
    assert summary["per_item"][item["id"]]["rubric_score"] == 0.5  # Round 2 failed a veto.
    assert summary["overhead"]["repairs"] == 1
    with (tmp_path / "runs.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["veto_failed"] for r in rows] == ["0", "1"]
    assert rows[0]["citation_recall"] == ""  # Refusal: not applicable.
    assert "全题平均" in (tmp_path / "summary.md").read_text(encoding="utf-8")
