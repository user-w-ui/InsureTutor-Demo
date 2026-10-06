"""Contracts for the judge-facing evaluation set in ``tests/eval/items.json``.

These tests do not run the tutor. They guard the *dataset itself*: that every
evidence anchor still resolves against the cleaned artifact, that physical page
numbers stay one-based and match the unit, that the items which must never be
answered with a single number stay marked as such, and that the vague-question
items stay genuinely vague instead of drifting into answerable — and therefore
useless — questions.

If ``data/cleaned/`` is regenerated, these fail loudly rather than letting the
evaluation set drift away from the corpus it grades against.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS_PATH = Path(__file__).resolve().parent / "items.json"
UNITS_PATH = ROOT / "data" / "cleaned" / "units.jsonl"
REPORT_PATH = ROOT / "data" / "cleaned" / "report.json"
RETRIEVAL_CASES_PATH = ROOT / "tests" / "retrieval_cases.json"

SCHEMA = "insuretutor.eval-set/2"
EXPECTED_ITEM_COUNT = 10
ITEM_FIELDS = [
    "id",
    "capability",
    "answer_mode",
    "question",
    "question_languages",
    "scenario_note",
    "accepted_statuses",
    "expected_answer",
    "evidence",
    "rubric",
    "veto_rubric",
    "bonus_rubric",
    "wrong_answers",
    "source_issues",
]
EVIDENCE_FIELDS = ["unit_id", "pdf_page", "quotes", "note"]
ISSUE_FIELDS = ["unit_id", "kind", "detail", "guidance"]
ISSUE_KINDS = {"language_conflict", "presentational_difference", "source_defect"}

CAPABILITIES = {
    "concept-separation",
    "citation-integrity",
    "numeric-precision",
    "citation-calculation",
    "edge-case-eligibility",
    "cross-language",
    "scope-refusal",
    "vague-request-triage",
}

ANSWER_MODES = {"explain", "numeric", "show-conflict", "refuse"}


def load_items():
    return json.loads(ITEMS_PATH.read_text(encoding="utf-8"))


def load_units():
    rows = [
        json.loads(line) for line in UNITS_PATH.read_text(encoding="utf-8").splitlines() if line
    ]
    return {row["id"]: row for row in rows}


def evidence(item):
    """Every evidence entry with its role, required first."""
    return [(role, e) for role in ("required", "supporting") for e in item["evidence"][role]]


class EvalSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_items()
        cls.items = cls.doc["items"]
        cls.units = load_units()
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    # ---- shape -----------------------------------------------------------

    def test_schema_and_fixed_field_order(self):
        """One shape for every item, so the judge and the scorer never guess."""
        self.assertEqual(self.doc["schema"], SCHEMA)
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertEqual(list(item), ITEM_FIELDS)
                self.assertEqual(list(item["evidence"]), ["required", "supporting"])
                for _, entry in evidence(item):
                    self.assertEqual(list(entry), EVIDENCE_FIELDS)
                    self.assertTrue(entry["quotes"], "every entry quotes the source")
                    self.assertLessEqual(set(entry["quotes"]), {"zh-Hant", "en"})
                    self.assertTrue(entry["note"].strip())
                for issue in item["source_issues"]:
                    self.assertEqual(list(issue), ISSUE_FIELDS)
                    self.assertIn(issue["kind"], ISSUE_KINDS)

    def test_item_count_and_ids_are_unique(self):
        self.assertEqual(len(self.items), EXPECTED_ITEM_COUNT)
        ids = [item["id"] for item in self.items]
        self.assertEqual(len(set(ids)), EXPECTED_ITEM_COUNT)

    def test_every_item_has_question_answer_evidence_and_rubric(self):
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["question"].strip())
                self.assertTrue(item["scenario_note"].strip())
                self.assertTrue(item["expected_answer"].startswith("结论："))
                self.assertIn(item["answer_mode"], ANSWER_MODES)
                self.assertIn(item["capability"], CAPABILITIES)
                self.assertTrue(item["rubric"], "every item needs grading guidance")
                if item["answer_mode"] != "refuse":
                    self.assertTrue(
                        item["evidence"]["required"], "an answer needs required evidence"
                    )

    def test_language_mix_is_exercised(self):
        """The set must not be monolingual: Simplified, Traditional and English."""
        langs = set()
        for item in self.items:
            langs.update(item["question_languages"])
        self.assertIn("zh-Hans", langs)
        self.assertIn("zh-Hant", langs)
        self.assertIn("en", langs)

    def test_simplified_characters_actually_appear_in_questions(self):
        """Simplified-only forms that never occur in Traditional body text.

        The class is restricted to characters whose Traditional counterpart is a
        *different* codepoint. Shared glyphs such as 不 / 個 / 沒 occur in both
        scripts, so they cannot distinguish a Simplified question from a
        Traditional quote and must stay out of the class.
        """
        blob = "\n".join(item["question"] for item in self.items)
        self.assertTrue(re.search(r"[这个们时发对还不没点样价会与为]", blob))

    # ---- evidence anchors resolve ----------------------------------------

    def test_evidence_resolves_to_the_unit_and_its_physical_page(self):
        for item in self.items:
            seen = set()
            for role, entry in evidence(item):
                uid = entry["unit_id"]
                with self.subTest(item=item["id"], role=role, unit=uid):
                    self.assertIn(uid, self.units)
                    self.assertIn(entry["pdf_page"], self.units[uid]["pages"])
                    self.assertGreaterEqual(entry["pdf_page"], 1)
                    self.assertLessEqual(entry["pdf_page"], 20)
                    self.assertNotIn(uid, seen, "a unit is listed once per item")
                    seen.add(uid)

    def test_quoted_evidence_occurs_in_the_cleaned_unit(self):
        """A quote may be trimmed, but every whitespace-separated fragment of it
        must appear literally in the unit's text in that language. This is the
        same substring standard the runtime citation verifier is held to."""
        for item in self.items:
            for role, entry in evidence(item):
                segments = {
                    r["language"]: r["text"] for r in self.units[entry["unit_id"]]["segments"]
                }
                for language, quote in entry["quotes"].items():
                    with self.subTest(
                        item=item["id"], role=role, unit=entry["unit_id"], language=language
                    ):
                        self.assertIn(language, segments)
                        for fragment in re.split(r"\s+", quote.strip()):
                            if fragment:
                                self.assertIn(fragment, segments[language])

    def test_quotes_stay_traditional_but_questions_may_be_simplified(self):
        """Guard the one-way t2s rule: a citable quote keeps Traditional forms.

        Quotations come from the corpus and are graded by substring, so any
        Simplified fold in a quote would be unciteable. Questions are the other
        way round and are expected to be mixed on purpose.
        """
        simplified_only = re.compile(r"[账额险费计划选单们这个时发对还点样价会与为]")
        for item in self.items:
            for _, entry in evidence(item):
                quote = entry["quotes"].get("zh-Hant")
                if quote:
                    with self.subTest(item=item["id"], unit=entry["unit_id"]):
                        self.assertIsNone(simplified_only.search(quote))

    def test_retrieval_core_targets_are_listed_as_evidence(self):
        """The retrieval benchmark and the answer set must not disagree on what is relevant."""
        cases = json.loads(RETRIEVAL_CASES_PATH.read_text(encoding="utf-8"))["cases"]
        by_prefix = {item["id"].split("-")[0]: item for item in self.items}
        for case in cases:
            listed = {e["unit_id"] for _, e in evidence(by_prefix[case["id"]])}
            with self.subTest(case=case["id"]):
                self.assertLessEqual(set(case["core"]), listed)

    # ---- the two rules that must never be relaxed -----------------------

    def test_conflict_item_forbids_a_single_answer(self):
        conflict = [i for i in self.items if i["answer_mode"] == "show-conflict"]
        self.assertEqual(len(conflict), 1)
        item = conflict[0]
        issues = [s for s in item["source_issues"] if s["kind"] == "language_conflict"]
        self.assertEqual(len(issues), 1)
        recorded = {c["unit"] for c in self.report["conflicts"]}
        self.assertIn(issues[0]["unit_id"], recorded)
        # Both languages must be quoted, or "show both" is not gradeable.
        entry = next(e for _, e in evidence(item) if e["unit_id"] == issues[0]["unit_id"])
        self.assertEqual(set(entry["quotes"]), {"zh-Hant", "en"})

    def test_scope_refusal_items_carry_no_required_evidence(self):
        """A refusal has no answerable claim, but must still name its basis.

        There are three refusals for three *different* reasons: q7 asks for data
        this brochure does not publish (2025 figures); q9 asks about three lines
        of cover the brochure was never about (medical, travel, motor); q10 asks
        who may take out *this* product, and the brochure states only an issue
        age. ``supporting`` holds the units a grader reads to see why the refusal
        is right.
        """
        refusals = [i for i in self.items if i["answer_mode"] == "refuse"]
        self.assertEqual(len(refusals), 3)
        for item in refusals:
            with self.subTest(item=item["id"]):
                self.assertEqual(item["evidence"]["required"], [])
                self.assertTrue(item["evidence"]["supporting"])

    def test_every_numeric_item_states_the_expected_number(self):
        for item in self.items:
            if item["answer_mode"] == "numeric":
                with self.subTest(item=item["id"]):
                    self.assertRegex(item["expected_answer"].splitlines()[0], r"\d")

    def test_answers_carry_no_pipeline_internals(self):
        """The judge grades against brochure facts, not against how we parsed them.

        v1 answers asked for MinerU block types, manifest paths and review labels
        that the tutor never sees; the reference answer may name pages, never
        the pipeline.
        """
        internal = re.compile(
            r"aside_text|block_index|manifest|MinerU|reviewed_source_conflict|unit_id|"
            r"items\.json|第\s*\d+\s*(?:-\s*\d+\s*)?单元"
        )
        for item in self.items:
            with self.subTest(item=item["id"]):
                for text in [item["expected_answer"], item["scenario_note"], *item["rubric"]]:
                    self.assertIsNone(internal.search(text), text)

    def test_tmp_render_pages_are_not_required(self):
        """The set must grade against the corpus, not against scratch renders."""
        blob = ITEMS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("tmp/pages", blob)

    # ---- the vague-question items ----------------------------------------

    def test_vague_items_read_like_a_real_user(self):
        """The low-information items must stay genuinely underspecified.

        They exist to test triage and retrieval, so they must not smuggle in the
        corpus's own terminology: the moment a question names the option, the
        unit id, or a currency figure, it stops testing anything.
        """
        leaked = re.compile(
            r"定期提款|額外回報|額外利息|保證可保|現金價值|基本保障額|派息率|"
            r"USD|US\$|HK\$|MOP|保單週年|附件|附註"
        )
        vague = [i for i in self.items if i["capability"] == "vague-request-triage"]
        self.assertGreaterEqual(len(vague), 1)
        for item in vague:
            with self.subTest(item=item["id"]):
                self.assertIsNone(leaked.search(item["question"]))
                self.assertLess(len(item["question"]), 60, "a vague question is short")

    def test_questions_do_not_tell_the_tutor_where_to_cite(self):
        """The question must not do the retrieval for the agent.

        A question that says "which footnote did you use", "give the citation
        location", or "根据第X页" hands over the answer's provenance and measures
        nothing but obedience. Those requirements belong in ``rubric``.

        Exception, deliberately kept: asking for the *figures* in all three
        currencies (q2) is a content requirement, not a pointer to a location.
        """
        pointing = re.compile(
            r"引用|引用位置|引用出处|citation|cite the page|cite your source|"
            r"哪一条脚注|哪條附註|用哪一条|用哪條|根据第\s*\d+\s*页|根據第\s*\d+\s*頁|"
            r"第\s*\d+\s*页(?:的|原文)|from which page|which page"
        )
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertIsNone(pointing.search(item["question"]))
                for _, entry in evidence(item):
                    self.assertNotIn(entry["unit_id"], item["question"])

    # ---- scoring fields -----------------------------------------------------

    def test_accepted_statuses_follow_answer_mode(self):
        """Offline status scoring reads these; a refusal can never accept a bare answer."""
        base = {
            "explain": {"answered"},
            "numeric": {"answered"},
            "show-conflict": {"source_conflict"},
            "refuse": {"refused", "insufficient"},
        }
        for item in self.items:
            with self.subTest(item=item["id"]):
                accepted = set(item["accepted_statuses"])
                self.assertEqual(len(accepted), len(item["accepted_statuses"]))
                self.assertLessEqual(base[item["answer_mode"]], accepted)
                # Only a vague request may also accept a clarification.
                extra = accepted - base[item["answer_mode"]]
                self.assertLessEqual(extra, {"clarification"})
                if extra:
                    self.assertEqual(item["capability"], "vague-request-triage")

    def test_veto_and_bonus_rubric_lines_exist_and_do_not_overlap(self):
        """One-based rubric line numbers; a line is required, veto, or bonus, never two."""
        for item in self.items:
            veto, bonus = item["veto_rubric"], item["bonus_rubric"]
            with self.subTest(item=item["id"]):
                for line in veto + bonus:
                    self.assertIsInstance(line, int)
                    self.assertGreaterEqual(line, 1)
                    self.assertLessEqual(line, len(item["rubric"]))
                self.assertEqual(len(set(veto)), len(veto))
                self.assertEqual(len(set(bonus)), len(bonus))
                self.assertFalse(set(veto) & set(bonus))
                self.assertLess(len(bonus), len(item["rubric"]), "an item needs a required line")
                for n, text in enumerate(item["rubric"], 1):
                    self.assertEqual(text.startswith("加分项："), n in bonus, text)


if __name__ == "__main__":
    unittest.main()
