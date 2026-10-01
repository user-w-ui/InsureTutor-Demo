"""Contracts for the judge-facing evaluation set in ``tests/eval/items.json``.

These tests do not run the tutor. They guard the *dataset itself*: that every
citation anchor in the answer key still resolves against the cleaned artifact,
that physical page numbers stay one-based and match the unit, that the items
which must never be answered with a single number stay marked as such, and that
the vague-question items stay genuinely vague instead of drifting into
answerable — and therefore useless — questions.

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
SPANS_PATH = ROOT / "data" / "cleaned" / "spans.jsonl"
REPORT_PATH = ROOT / "data" / "cleaned" / "report.json"

EXPECTED_ITEM_COUNT = 10

# Items that carry no answerable claim and so anchor to nothing. ``refuse`` says
# the question is out of the brochure's scope; ``clarify`` says the question is
# in scope but too underspecified to answer yet. Both must ask before asserting.
NO_CITATION_MODES = {"refuse"}
# ``clarify`` may still cite (to pin down *which* product is meant) but is not
# required to, because the honest answer at that point is a question back.

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

ANSWER_MODES = {"explain", "numeric", "show-conflict", "refuse", "clarify"}


def load_items():
    return json.loads(ITEMS_PATH.read_text(encoding="utf-8"))


def load_units():
    rows = [json.loads(line) for line in UNITS_PATH.read_text(encoding="utf-8").splitlines() if line]
    return {row["id"]: row for row in rows}


def load_spans():
    rows = [json.loads(line) for line in SPANS_PATH.read_text(encoding="utf-8").splitlines() if line]
    return {row["id"]: row for row in rows}


class EvalSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_items()
        cls.items = cls.doc["items"]
        cls.units = load_units()
        cls.spans = load_spans()
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    # ---- shape -----------------------------------------------------------

    def test_item_count_and_ids_are_unique(self):
        self.assertEqual(len(self.items), EXPECTED_ITEM_COUNT)
        ids = [item["id"] for item in self.items]
        self.assertEqual(len(set(ids)), EXPECTED_ITEM_COUNT)

    def test_every_item_has_question_answer_citations_and_rubric(self):
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["question"].strip())
                self.assertTrue(item["expected_answer"].strip())
                self.assertIn(item["answer_mode"], ANSWER_MODES)
                if item["answer_mode"] in NO_CITATION_MODES:
                    # A refusal has no answerable claim, so it anchors to nothing;
                    # test_scope_refusal_item_has_no_answerable_number enforces that.
                    self.assertEqual(item["citations"], [])
                else:
                    self.assertTrue(item["citations"], "every answerable item needs a citation anchor")
                self.assertTrue(item["rubric"], "every item needs grading guidance")
                self.assertIn(item["capability"], CAPABILITIES)

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

    # ---- citation anchors resolve ---------------------------------------

    def test_every_cited_unit_exists(self):
        for item in self.items:
            for citation in item["citations"]:
                with self.subTest(item=item["id"], unit=citation["unit_id"]):
                    self.assertIn(citation["unit_id"], self.units)

    def test_physical_page_matches_the_unit_item(self):
        for item in self.items:
            for citation in item["citations"]:
                unit = self.units[citation["unit_id"]]
                with self.subTest(item=item["id"], unit=citation["unit_id"]):
                    self.assertIn(citation["pdf_page"], unit["pages"])

    def test_cited_pages_are_one_based_and_in_range(self):
        for item in self.items:
            for citation in item["citations"]:
                with self.subTest(item=item["id"], unit=citation["unit_id"]):
                    self.assertGreaterEqual(citation["pdf_page"], 1)
                    self.assertLessEqual(citation["pdf_page"], 20)

    def test_quoted_evidence_occurs_in_the_cleaned_unit(self):
        """A quote may be trimmed, but every whitespace-separated fragment of it
        must appear literally in the unit's text. This is the same substring
        standard the runtime citation verifier is held to."""
        for item in self.items:
            for citation in item["citations"]:
                quote = citation["quote"]
                unit_text = next(r["text"] for r in self.units[citation["unit_id"]]["segments"]
                                 if r["language"] == citation["language"])
                with self.subTest(item=item["id"], unit=citation["unit_id"]):
                    for fragment in re.split(r"\s+", quote.strip()):
                        if not fragment:
                            continue
                        self.assertIn(
                            fragment, unit_text,
                            f"{item['id']}: fragment {fragment!r} not found in {citation['unit_id']}",
                        )

    def test_requires_links_are_declared_for_footnote_dependent_answers(self):
        """Items whose answer depends on a numbered note must cite a unit that
        declares that note via requires / note_refs, so retrieval completion
        cannot silently drop it."""
        for item in self.items:
            for note in item.get("depends_on_notes", []):
                with self.subTest(item=item["id"], note=note):
                    reached = any(
                        note in self.units[citation["unit_id"]]["note_refs"]
                        or f"note-{note}" in self.units[citation["unit_id"]]["requires"]
                        or citation["unit_id"] == f"note-{note}"
                        for citation in item["citations"]
                    )
                    self.assertTrue(reached, f"{item['id']} does not reach note {note}")

    # ---- the two rules that must never be relaxed -----------------------

    def test_conflict_item_forbids_a_single_answer(self):
        conflict = [i for i in self.items if i["answer_mode"] == "show-conflict"]
        self.assertEqual(len(conflict), 1)
        item = conflict[0]
        self.assertTrue(item["must_not_pick_one"])
        recorded = {c["unit"] for c in self.report["conflicts"]}
        self.assertIn(item["conflicts"][0]["unit_id"], recorded)
        self.assertEqual(item["conflicts"][0]["status"], "reviewed_source_conflict")
        # Both languages must be present, or "show both" is not gradeable.
        langs = {c["language"] for c in item["conflicts"][0]["values"]}
        self.assertEqual(langs, {"zh-Hant", "en"})

    def test_scope_refusal_items_carry_no_answerable_number(self):
        """Every refusal must be citation-free and explicitly non-fabricating.

        There are three refusals and they are refusing for three *different*
        reasons, which is the point. q7 refuses a question about data this
        edition of *this* product does not publish (2025 crediting figures);
        q9 refuses three lines of cover the brochure was never about (medical,
        travel, motor); q10 refuses a question that is squarely about this
        product — who may take it out — because the brochure states one
        qualification (age) and says nothing about residence. A refusal is not
        a shrug: each must name the basis on which it declines.
        """
        refusals = [i for i in self.items if i["answer_mode"] == "refuse"]
        self.assertEqual(len(refusals), 3)
        for item in refusals:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["must_not_fabricate"])
                self.assertEqual(item["citations"], [], "a refusal cites nothing")
                self.assertTrue(item["refusal_grounding"], "a refusal states its scope basis")

    def test_refusal_grounding_anchors_resolve(self):
        """A refusal cites nothing, so its *justification* has to stand on its own.

        ``refusal_grounding`` entries are deliberately not citations — the answer
        must not present them as support for a claim — but they name the units the
        grader will read to see why the refusal is correct, so a stale unit id or
        a wrong page number silently misleads the judge. They were unvalidated
        until q9 shipped with ``disclaimer-zh`` labelled page 17 when the unit is
        on page 19; the same whitespace-fragment rule as ``citations`` applies.
        """
        for item in self.items:
            for entry in item.get("refusal_grounding", []):
                unit_id = entry["unit_id"]
                with self.subTest(item=item["id"], unit=unit_id):
                    self.assertIn(unit_id, self.units, "refusal grounding names a real unit")
                    unit = self.units[unit_id]
                    self.assertIn(
                        entry["pdf_page"], unit["pages"],
                        f"{item['id']}: {unit_id} is not on physical page {entry['pdf_page']}",
                    )
                    quote = entry.get("quote")
                    if quote:
                        for fragment in re.split(r"\s+", quote.strip()):
                            if fragment:
                               self.assertIn(fragment, next(r["text"] for r in unit["segments"]
                                            if r["language"] == entry["language"]))

    def test_every_numeric_item_states_the_expected_number(self):
        for item in self.items:
            if item["answer_mode"] == "numeric":
                with self.subTest(item=item["id"]):
                    self.assertRegex(item["expected_answer"], r"\d")

    def test_quotes_stay_traditional_but_questions_may_be_simplified(self):
        """Guard the one-way t2s rule: a citable quote keeps Traditional forms.

        Quotations come from the corpus and are graded by substring, so any
        Simplified fold in a quote would be unciteable. Questions are the other
        way round and are expected to be mixed on purpose.
        """
        simplified_only = re.compile(r"[账额险费计划选单们这个时发对还点样价会与为]")
        for item in self.items:
            for citation in item["citations"]:
                with self.subTest(item=item["id"], unit=citation["unit_id"]):
                    self.assertIsNone(
                        simplified_only.search(citation["quote"]),
                        "citable quote contains Simplified-only characters",
                    )

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

        The group held two items while "这个保险怎么样？" (clarify) sat alongside
        the grandson question (explain). It holds one now that the last item asks
        a real eligibility question — "我不是香港本地人能投保吗？" is short and
        keyword-free too, but it has a definite answer the brochure declines to
        give, so it is a scope refusal, not a triage case. Length and leakage are
        what make this group, not the count, so the count is asserted loosely.
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

        A judge is testing whether the tutor can find its own evidence. A question
        that says "which footnote did you use", "give the citation location", or
        "根据第X页" hands over the answer's provenance and measures nothing but
        obedience. Those instructions belong in ``rubric``, where they grade the
        answer, not in ``question``, which must read like a customer talking.

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
                self.assertIsNone(
                    pointing.search(item["question"]),
                    f"{item['id']}: the question points the tutor at a citation",
                )
                for citation in item["citations"]:
                    self.assertNotIn(
                        citation["unit_id"], item["question"],
                        f"{item['id']}: the question names a unit id",
                    )

    def test_answer_key_blockquote_matches_items_json_question(self):
        """``ANSWER_KEY.md`` and ``items.json`` are two views of one question.

        The key is the human-readable artifact a judge reads; ``items.json`` is
        what the tests and the harness consume. Nothing kept them in step, and
        they drifted the moment a question was edited in one place: after the
        "don't ask where to cite" edit, the key's Q4 blockquote still carried the
        dropped 「并说明你用哪一条脚注」 sentence for hours. A judge reading the key
        would have seen the tutor asked to hand over its provenance — the exact
        behaviour the edit removed — while every contract test passed.

        Comparing the blockquotes to ``items.json`` catches that, and it catches
        the milder drift too: a reworded question, a stray trailing space, a
        typo fixed in one file only.
        """
        key = (ITEMS_PATH.parent / "ANSWER_KEY.md").read_text(encoding="utf-8")
        # Author guidance sits in the body; the question is the blockquote under
        # the `## Qn —` heading, so collect all quoted lines and require each
        # question to appear verbatim among them.
        quoted = [line[2:].strip() for line in key.splitlines() if line.startswith("> ")]
        self.assertTrue(quoted, "the key quotes its questions")
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertIn(
                    item["question"].strip(),
                    quoted,
                    f"{item['id']}: ANSWER_KEY.md no longer quotes the current question",
                )

    def test_clarify_and_refuse_never_assert(self):
        """Neither mode may ship a settled answer in ``expected_answer``.

        ``clarify`` must pose a question back and withhold figures; ``refuse``
        must state the scope boundary. This is the guard against a future edit
        quietly turning either into an answerable item.
        """
        for item in self.items:
            if item["answer_mode"] == "clarify":
                with self.subTest(item=item["id"]):
                    self.assertIn("澄清", item["expected_answer"])
                    self.assertTrue(
                        any(q in item["expected_answer"] for q in ("？", "?")),
                        "a clarify item must ask something back",
                    )
            if item["answer_mode"] == "refuse":
                with self.subTest(item=item["id"]):
                    self.assertTrue(item["refusal_grounding"], "a refusal states its scope basis")


if __name__ == "__main__":
    unittest.main()
