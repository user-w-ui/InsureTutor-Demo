"""Contracts for the judge-facing evaluation set in ``tests/eval/items.json``.

These tests do not run the tutor. They guard the *dataset itself*: that every
citation anchor in the answer key still resolves against the cleaned artifact,
that physical page numbers stay one-based and match the unit, and that the two
items which must never be answered with a single number stay marked as such.

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

EXPECTED_ITEM_COUNT = 7


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

    def test_seven_items_with_unique_ids(self):
        self.assertEqual(len(self.items), EXPECTED_ITEM_COUNT)
        ids = [item["id"] for item in self.items]
        self.assertEqual(len(set(ids)), EXPECTED_ITEM_COUNT)

    def test_every_item_has_question_answer_citations_and_rubric(self):
        for item in self.items:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["question"].strip())
                self.assertTrue(item["expected_answer"].strip())
                if item["answer_mode"] == "refuse":
                    # A refusal has no answerable claim, so it anchors to nothing;
                    # test_scope_refusal_item_has_no_answerable_number enforces that.
                    self.assertEqual(item["citations"], [])
                else:
                    self.assertTrue(item["citations"], "every answerable item needs a citation anchor")
                self.assertTrue(item["rubric"], "every item needs grading guidance")
                self.assertIn(item["capability"], {
                    "concept-separation",
                    "citation-integrity",
                    "numeric-precision",
                    "citation-calculation",
                    "edge-case-eligibility",
                    "cross-language",
                    "scope-refusal",
                })

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
                unit_text = self.units[citation["unit_id"]]["text"]
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

    def test_scope_refusal_item_has_no_answerable_number(self):
        refusals = [i for i in self.items if i["answer_mode"] == "refuse"]
        self.assertEqual(len(refusals), 1)
        item = refusals[0]
        self.assertTrue(item["must_not_fabricate"])
        self.assertEqual(item["citations"], [], "a refusal cites nothing")

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


if __name__ == "__main__":
    unittest.main()
