"""Regression checks against the brochure's observed ingestion failure modes."""

import copy
import json
import unittest
import uuid

from insuretutor.ingest.clean import (
    PDF,
    RAW,
    RULES,
    ROOT,
    TableParser,
    build,
    digest,
    expand_required,
    normalize,
    write_outputs,
)


class CleaningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_bytes = RAW.read_bytes()
        cls.pdf_bytes = PDF.read_bytes()
        cls.rules_bytes = RULES.read_bytes()
        cls.rules = json.loads(cls.rules_bytes)
        cls.raw = json.loads(cls.raw_bytes)
        cls.result = build(cls.raw_bytes, cls.rules, cls.pdf_bytes)
        cls.units = {u["id"]: u for u in cls.result["units"]}
        cls.spans = {s["source_key"]: s for s in cls.result["spans"]}

    def test_all_input_blocks_accounted_for_and_layout_noise_not_indexed(self):
        ledger = self.result["ledger"]
        self.assertEqual(list(range(380)), [row["block_index"] for row in ledger])
        excluded = {row["block_index"] for row in ledger
                    if row["action"] in {"excluded_layout_noise", "metadata_only"}}
        self.assertEqual(len(excluded), 39)
        by_id = {s["id"]: s for s in self.result["spans"]}
        for unit in self.units.values():
            for sid in unit["source_span_ids"] + unit["context_span_ids"]:
                self.assertNotIn(by_id[sid]["block_index"], excluded)
        text = "\n".join(u["text"] for u in self.units.values())
        self.assertNotIn("MANACLTENT", text)
        self.assertNotIn("PSP-137-V3-0925B", text)

    def test_disclaimer_rescued_and_version_saved_as_metadata(self):
        self.assertIn("does not contain the full terms", self.units["disclaimer-en"]["text"])
        self.assertEqual(self.units["disclaimer-en"]["pages"], [19])
        self.assertEqual(self.result["manifest"]["metadata"]["version_code"]["raw_text"],
                         "PSP-137-V3-0925B")

    def test_reference_markup_is_not_exponent_or_ordinal(self):
        self.assertEqual(normalize("51<sup>st</sup> and $20^{th}$")[0], "51st and 20th")
        self.assertEqual(normalize("x<sup>2</sup>")[0], "x^{2}")
        self.assertEqual(normalize("x<sub>2</sub>")[0], "x_{2}")
        self.assertEqual(normalize("Option<sup>3</sup>", markup_refs=[3])[:2],
                         ("Option", [3]))
        self.assertEqual(normalize(r"&quot;Account Value&quot; \$708,800")[0],
                         '"Account Value" $708,800')

    def test_bare_numbers_are_removed_only_at_pinned_locations(self):
        text = "age 51, 25%, 3 years, HK$400,000"
        self.assertEqual(normalize(text), (text, [], []))
        self.assertEqual(self.units["table-97-row-1"]["note_refs"], [4])
        self.assertEqual(self.units["table-97-row-3"]["note_refs"], [5])
        self.assertNotIn('Insured"4', self.units["table-97-row-1"]["text"])
        self.assertIn("25%", self.units["note-3"]["text"])
        self.assertIn("51st", self.units["note-3"]["text"])
        self.assertIn("50%", self.units["table-97-row-3"]["text"])

    def test_reference_removal_preserves_english_word_boundary(self):
        text = self.units["table-356-row-1"]["text"]
        self.assertIn("withdrawal charge of US$25", text)
        self.assertNotIn("chargeof", text)

    def test_ten_note_pairs_and_missing_six_label(self):
        for number in range(1, 11):
            note = self.units[f"note-{number}"]
            self.assertEqual(len(note["source_span_ids"]), 2)
            self.assertEqual(note["pages"], [12])
        self.assertEqual(self.spans["b202"]["raw_text"], self.raw[202]["text"])
        self.assertFalse(self.spans["b202"]["raw_text"].startswith("6."))
        self.assertIn("生效滿10年", self.units["note-6"]["text"])

    def test_required_evidence_closure(self):
        bundle = expand_required(self.result["units"], ["withdrawal"])
        ids = {u["id"] for u in bundle}
        self.assertTrue({"withdrawal", "note-6", "note-7", "cash-value-risk", "term-and-lapse"} <= ids)
        self.assertEqual(len(ids), len(bundle))
        bundle = expand_required(self.result["units"], ["table-352-row-8"])
        self.assertIn("note-3", {u["id"] for u in bundle})
        bundle = expand_required(self.result["units"], ["table-352-row-2"])
        self.assertTrue({"rate-date-note", "interest-year20-note", "interest-every5-note"}
                        <= {u["id"] for u in bundle})

    def test_fee_rows_keep_non_guaranteed_fee_note(self):
        for key in ("table-354-row-6", "table-354-row-7", "table-354-row-8", "table-356-row-0"):
            self.assertIn("note-10", self.units[key]["requires"])
        self.assertIn("10%", self.units["table-354-row-6"]["text"])
        self.assertIn("14", self.units["table-356-row-0"]["text"])

    def test_merged_cells_keep_age_headers_and_amounts(self):
        unit = self.units["table-354-row-1"]
        self.assertIn("< Age 45 歲: 香港保單", unit["text"])
        self.assertIn("≥ Age 45 歲: US$15,000", unit["text"])
        self.assertIn("FP80/100/130", unit["text"])
        other = self.units["table-354-row-3"]
        self.assertIn("< Age 45 歲 / ≥ Age 45 歲: US$5,000", other["text"])
        table = next(t for t in self.result["tables"] if t["block_index"] == 354)
        self.assertEqual(table["grid"][1][0], table["grid"][3][0])

    def test_table_expansion_rejects_overlapping_cells(self):
        parser = TableParser()
        parser.feed('<table><tr><td>A</td><td rowspan="2">B</td></tr>'
                    '<tr><td colspan="2">C</td></tr></table>')
        with self.assertRaises(ValueError):
            parser.expanded("test")

    def test_stuck_values_split_by_exact_source_substrings(self):
        early = self.units["table-352-row-5-early"]["text"]
        later = self.units["table-352-row-5-later"]["text"]
        self.assertIn("2.75%", early)
        self.assertIn("15/20/25", early)
        self.assertNotIn("5.5%", early)
        self.assertIn("5.5%", later)
        self.assertIn("30th", later)
        self.assertNotIn("2.75%", later)
        for span in self.spans.values():
            if "parent_source_key" in span:
                parent = self.spans[span["parent_source_key"]]["raw_text"]
                start, end = span["raw_char_range"]
                self.assertEqual(parent[start:end], span["raw_text"])

    def test_conflict_survives_without_choosing_a_currency_amount(self):
        unit = self.units["table-354-row-5"]
        self.assertTrue(unit["conflict"])
        self.assertEqual(unit["pages"], [17])
        self.assertIn("40,000港元 / 400,000澳門元", unit["text"])
        self.assertIn("HK$400,000 / MOP40,000", unit["text"])
        self.assertEqual(unit["pairing_status"], "reviewed_source_conflict")

    def test_damaged_text_repaired_only_with_recorded_pdf_corrections(self):
        self.assertEqual(self.result["report"]["control_character_occurrences"], 4)
        for key, count in (("b115", 1), ("b200", 1), ("b201", 2)):
            span = self.spans[key]
            self.assertIn("\x1a", span["raw_text"])
            self.assertNotIn("\x1a", span["clean_text"])
            self.assertEqual(span["clean_text"].count("總"), count)
            self.assertNotIn("damaged_text", span["quality_flags"])
            self.assertEqual(span["text_origin"], "pdf_verified")
            self.assertEqual(span["raw_block_indices"], [span["block_index"]])
            self.assertIn("PDF", span["quote_policy"])
        self.assertTrue(self.spans["b224"]["clean_text"].startswith("投資回報："))
        self.assertTrue(self.spans["b225"]["clean_text"].startswith("退保："))
        report = self.result["report"]
        self.assertEqual(report["resolved_issue_count"], 7)
        self.assertEqual(report["unresolved_issue_count"], 0)
        self.assertEqual(report["status"], "cleaned_ready_for_chunking")
        for span in self.spans.values():
            for field in ("clean_text", "evidence_text"):
                self.assertNotRegex(span[field], r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
                self.assertNotIn("[解析缺字]", span[field])

    def test_missing_captions_not_fabricated(self):
        self.assertEqual(sum(t["caption"] is not None for t in self.result["tables"]), 2)
        self.assertIsNone(next(t for t in self.result["tables"] if t["block_index"] == 97)["caption"])
        self.assertEqual(next(t for t in self.result["tables"] if t["block_index"] == 356)["caption"],
                         ["保單資料 Policy Information"])

    def test_parallel_text_grouped_and_pdf_formulas_restored(self):
        unit = self.units["insurability"]
        self.assertEqual(unit["source_keys"], ["b89", "b90"])
        self.assertEqual(unit["evidence_group"], self.units["table-352-row-8"]["evidence_group"])
        self.assertIn("asset-allocation-row-1", self.units)
        self.assertNotIn("table-231-row-1", self.units)
        expected = {
            "extra-bonus-formula": (9, "額外回報 = 過往5年的平均每月賬戶價值 × 額外回報率"),
            "cash-value-formula": (10, "現金價值 = 賬戶價值 − 適用的退保費用"),
        }
        for key, (page, text) in expected.items():
            formula = self.units[key]
            self.assertTrue(formula["indexable"])
            self.assertEqual(formula["pages"], [page])
            self.assertEqual(formula["review_status"], "pdf_verified")
            self.assertIn(text, formula["text"])
        for key, title in (("generic-coverage", "Flexible Coverage"),
                           ("generic-premium-rate", "Preferential Premium Rates"),
                           ("generic-payment-flexibility", "Premium Flexibility"),
                           ("generic-cash-withdrawal", "Flexible cash withdrawal")):
            zh, en = self.units[key]["segments"]
            self.assertEqual(en["title"], title)
            self.assertNotRegex(zh["text"], "[A-Za-z]")
            self.assertEqual(self.units[key]["pages"], [4])
        self.assertIn("省卻額外保單費用", self.units["generic-coverage"]["text"])
        self.assertIn("無須支付貸款利息", self.units["generic-payment-flexibility"]["text"])
        self.assertIn("$708,800 × 2.75% = $19,492", self.units["bonus-example"]["text"])
        self.assertTrue({"example-disclaimer", "bonus-rate-disclaimer"}
                        <= set(self.units["bonus-example"]["requires"]))

    def test_changed_input_or_stale_literal_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Source hash"):
            build(self.raw_bytes + b" ", self.rules, self.pdf_bytes)
        rules = copy.deepcopy(self.rules)
        rules["literal_markers"]["b83"][0]["anchor"] = "NOT IN SOURCE1"
        with self.assertRaisesRegex(ValueError, "anchor"):
            build(self.raw_bytes, rules, self.pdf_bytes)

    def test_reproducible_outputs_and_original_files_unchanged(self):
        second = build(self.raw_bytes, self.rules, self.pdf_bytes)
        self.assertEqual(second, self.result)
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        # Normal inherited permissions also work inside the Windows restricted token;
        # tempfile's private 0700 directory can exclude that token on newer Python.
        folder = scratch / ("cleaning-test-" + uuid.uuid4().hex)
        folder.mkdir()
        self.assertTrue(folder.resolve().is_relative_to(scratch.resolve()))
        a, b = folder / "a", folder / "b"
        try:
            write_outputs(self.result, a, self.rules_bytes)
            write_outputs(second, b, self.rules_bytes)
            self.assertEqual({p.name: p.read_bytes() for p in a.iterdir()},
                             {p.name: p.read_bytes() for p in b.iterdir()})
        finally:
            for directory in (a, b):
                if directory.exists():
                    for artifact in directory.iterdir():
                        artifact.unlink()
                    directory.rmdir()
            folder.rmdir()
        self.assertEqual(digest(RAW.read_bytes()), self.rules["raw_sha256"])
        self.assertEqual(digest(PDF.read_bytes()), self.rules["pdf_sha256"])


if __name__ == "__main__":
    unittest.main()
