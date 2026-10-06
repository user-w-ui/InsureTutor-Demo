"""Offline corpus contracts: coverage, citation provenance and complete conditions."""

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from opencc import OpenCC
from pydantic import ValidationError

from insuretutor.corpus import (
    ROOT,
    Corpus,
    LogicalUnit,
    LanguageRecord,
    SourceSegment,
    SourceSpan,
    _views,
    assemble_evidence,
    build_corpus,
    corpus_bytes,
    load_tokenizer,
)


def read_rows(filename):
    return [json.loads(line) for line in
            (ROOT / "data/cleaned" / filename).read_text(encoding="utf-8").splitlines()]


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            cls.corpus = build_corpus()
        cls.tokenizer = load_tokenizer()
        cls.units = {u.id: u for u in cls.corpus.units}
        cls.spans = {s.id: s for s in cls.corpus.source_spans}

    def views(self, uid, language=None):
        return [v for v in self.corpus.retrieval_views if v.parent_unit_id == uid
                and (language is None or v.language == language)]

    def test_all_original_units_spans_and_relations_are_preserved(self):
        self.assertEqual(len(self.units), 137)
        self.assertEqual(len(self.spans), 660)
        self.assertEqual({s.language for s in self.spans.values()}, {"zh-Hant", "en"})
        for row in read_rows("units.jsonl"):
            actual = self.units[row["id"]].model_dump()
            self.assertEqual(row, {key: actual[key] for key in row})
        for row in read_rows("spans.jsonl"):
            self.assertEqual(row, self.spans[row["id"]].model_dump())

    def test_every_unit_has_complete_bilingual_views_and_english_has_no_chinese(self):
        for uid in self.units:
            self.assertEqual({v.language for v in self.views(uid)}, {"zh-Hans", "en"}, uid)
        for view in self.corpus.retrieval_views:
            if view.language == "en":
                self.assertIsNone(re.search(r"[\u3400-\u9fff\uf900-\ufaff]", view.search_text))

    def test_exhaustive_body_and_context_coverage(self):
        for unit in self.corpus.units:
            views = self.views(unit.id)
            ids = unit.source_span_ids + self.corpus.context_by_unit[unit.id]
            for peer in self.corpus.parallel_units.get(unit.id, []):
                ids += self.units[peer].source_span_ids
            for sid in dict.fromkeys(ids):
                text = self.spans[sid].evidence_text
                for part in self.corpus.language_segments[sid]:
                    matching = [v for v in views if part.language == "shared"
                                or v.language == ("en" if part.language == "en" else "zh-Hans")]
                    covered = {i for v in matching for p in v.source_segments
                               if p.span_id == sid for i in range(p.start, p.end)}
                    self.assertTrue(all(i in covered for i in range(part.start, part.end)),
                                    (unit.id, sid, repr(text[part.start:part.end])))
        for view in self.corpus.retrieval_views:
            for ref in view.source_segments:
                self.assertTrue(self.spans[ref.span_id].evidence_text[ref.start:ref.end])

    def test_token_counts_include_e5_prefix_and_special_tokens_without_truncation(self):
        for view in self.corpus.retrieval_views:
            encoding = self.tokenizer.encode(view.search_text, add_special_tokens=True)
            self.assertTrue(view.search_text.startswith("passage: "))
            self.assertEqual(view.token_count, len(encoding.ids))
            self.assertLessEqual(view.token_count, 512)
            self.assertEqual(encoding.tokens[0], "<s>")
            self.assertEqual(encoding.tokens[-1], "</s>")

    def test_simplified_search_never_changes_original_quotes(self):
        zh = self.views("withdrawal", "zh-Hans")[0]
        self.assertIn("现金价值", zh.search_text)
        self.assertNotIn("現金價值", zh.search_text)
        bundle = assemble_evidence(self.corpus, ["withdrawal"])
        original = next(s for s in bundle.source_spans if s.source_key == "b161")
        self.assertIn("現金價值", original.evidence_text)
        self.assertEqual(original.pdf_page, 10)
        self.assertEqual(original.bbox_raw, self.spans[original.id].bbox_raw)

    def test_table_header_number_and_language_association(self):
        for lang, header in [("en", "Policy Year: 15/20/25"),
                             ("zh-Hans", "保单年: 15/20/25")]:
            view = self.views("table-352-row-5-early", lang)[0]
            self.assertIn(header, view.search_text)
            self.assertIn("2.75%", view.search_text)
        for lang, prefix in [("en", "b252"), ("zh-Hans", "b231")]:
            view = self.views("asset-allocation-row-1", lang)[0]
            amounts = [s for s in view.source_segments
                       if s.role == "body" and not re.search(r"[A-Za-z\u3400-\u9fff]",
                                                            self.spans[s.span_id].evidence_text)]
            self.assertEqual(len(amounts), 1)
            self.assertIn(prefix, amounts[0].span_id)
            bundle = assemble_evidence(self.corpus, ["asset-allocation-row-1"])
            self.assertTrue(any(s.source_key == f"{prefix}:r0:c1" for s in bundle.source_spans))
        english = self.views("table-354-row-1", "en")[0].search_text
        self.assertIn("FP80/100/130", english)
        self.assertIn("< Age 45", english)
        self.assertIn("≥ Age 45", english)

    def test_required_notes_are_full_and_source_deduplicated(self):
        bundle = assemble_evidence(self.corpus, ["withdrawal", "withdrawal", "withdrawal-summary"])
        ids = {u.id for u in bundle.units}
        self.assertTrue({"withdrawal", "note-6", "note-7", "cash-value-risk", "term-and-lapse"} <= ids)
        self.assertEqual(bundle.selected_unit_ids, ["withdrawal", "withdrawal-summary"])
        self.assertEqual(len(bundle.source_spans), len({s.id for s in bundle.source_spans}))
        note = next(s for s in bundle.source_spans if s.source_key == "b202")
        self.assertEqual(note.evidence_text, self.spans[note.id].evidence_text)
        for condition in ["10年", "500美元/4,000港元/4,000澳門元", "年期最短一年", "年期最短三年", "手續費"]:
            self.assertIn(condition, note.evidence_text)
        insured = assemble_evidence(self.corpus, ["insurability"])
        self.assertIn("note-3", {u.id for u in insured.units})
        self.assertTrue(any("最多只可行使兩次" in s.evidence_text for s in insured.source_spans))

    def test_distinct_facts_with_the_same_topic_are_not_merged(self):
        bundle = assemble_evidence(self.corpus, ["coverage-summary", "coverage-change"])
        self.assertTrue({"coverage-summary", "coverage-change"} <= {u.id for u in bundle.units})
        self.assertEqual(self.units["coverage-summary"].evidence_group,
                         self.units["coverage-change"].evidence_group)

    def test_conflict_retains_both_literal_amounts_and_source_ranges(self):
        uid = "table-354-row-5"
        zh = self.views(uid, "zh-Hans")[0]
        en = self.views(uid, "en")[0]
        self.assertIn("40,000港元 / 400,000澳门元", zh.search_text)
        self.assertIn("HK$400,000 / MOP40,000", en.search_text)
        body_zh = next(s for s in zh.source_segments if s.role == "body")
        body_en = next(s for s in en.source_segments if s.role == "body")
        self.assertNotEqual(body_zh.span_id, body_en.span_id)
        self.assertEqual(self.spans[body_zh.span_id].origin_span_id,
                         self.spans[body_en.span_id].origin_span_id)
        bundle = assemble_evidence(self.corpus, [uid])
        self.assertIn(uid, bundle.conflicts)
        original = next(s for s in bundle.source_spans if s.id == body_zh.span_id)
        self.assertEqual(original.pdf_page, 17)
        self.assertIn("40,000港元", original.evidence_text[body_zh.start:body_zh.end])
        self.assertIn("HK$400,000", self.spans[body_en.span_id].evidence_text[body_en.start:body_en.end])

    def test_long_view_restores_the_complete_parent(self):
        children = self.views("terminal-exclusions", "en")
        self.assertGreater(len(children), 1)
        for child in children:
            bundle = assemble_evidence(self.corpus, [child.parent_unit_id])
            sources = {s.id: s for s in bundle.source_spans}
            for sid in self.units[child.parent_unit_id].source_span_ids:
                self.assertEqual(sources[sid].evidence_text, self.spans[sid].evidence_text)
            self.assertTrue(any("18 years" in s.evidence_text for s in bundle.source_spans))

    def test_independent_disclaimers_are_explicitly_connected_without_merging_ids(self):
        for uid in ["disclaimer-zh", "disclaimer-en"]:
            bundle = assemble_evidence(self.corpus, [uid])
            self.assertEqual({u.id for u in bundle.units}, {"disclaimer-zh", "disclaimer-en"})
            self.assertTrue({"b359", "b360"} <= {s.source_key for s in bundle.source_spans})

    def test_existing_evaluation_citations_still_resolve(self):
        items = json.loads((ROOT / "tests/eval/items.json").read_text(encoding="utf-8"))["items"]
        self.assertGreaterEqual(len(items), 7)
        for item in items:
            for entry in item["evidence"]["required"] + item["evidence"]["supporting"]:
                uid = entry["unit_id"]
                bundle = assemble_evidence(self.corpus, [uid])
                unit = self.units[uid]
                self.assertIn(entry["pdf_page"], unit.pages)
                sources = {s.id: s for s in bundle.source_spans}
                self.assertTrue(any(sources[sid].pdf_page == entry["pdf_page"]
                                    for sid in unit.source_span_ids + unit.context_span_ids))
                for quote in entry["quotes"].values():
                    for word in quote.split():
                        self.assertTrue(any(word in r.text for r in unit.segments))

    def test_offline_rebuild_is_byte_identical_and_inputs_remain_frozen(self):
        manifest_path = ROOT / "data/cleaned/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = [manifest_path] + [ROOT / "data/cleaned" / name
                                  for name in manifest["artifacts"]] + [
            ROOT / "raw data/source/FLEXI-ULife Prime Saver.pdf",
            ROOT / "raw data/mineru-official/content/FLEXI-ULife Prime Saver.json"]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            rebuilt = build_corpus()
        self.assertEqual(corpus_bytes(self.corpus), corpus_bytes(rebuilt))
        self.assertEqual(corpus_bytes(rebuilt), (ROOT / "data/corpus.json").read_bytes())
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_invalid_or_incomplete_corpus_fails_closed(self):
        original = self.corpus.model_dump()
        bad = copy.deepcopy(original)
        bad["units"][0]["requires"].append("missing-unit")
        with self.assertRaises(ValidationError):
            Corpus.model_validate(bad)
        bad = copy.deepcopy(original)
        bad["source_spans"][0]["language"] = "mixed"
        with self.assertRaises(ValidationError):
            Corpus.model_validate(bad)
        bad = copy.deepcopy(original)
        bad["units"][0]["segments"].pop()
        with self.assertRaises(ValidationError):
            Corpus.model_validate(bad)
        bad = copy.deepcopy(original)
        bad["retrieval_views"] = [v for v in bad["retrieval_views"]
                                  if v["id"] != "terminal-exclusions/en/002"]
        with self.assertRaises(ValidationError):
            Corpus.model_validate(bad)
        bad = copy.deepcopy(original)
        next(v for v in bad["retrieval_views"] if v["language"] == "en")["search_text"] += " 中文"
        with self.assertRaises(ValidationError):
            Corpus.model_validate(bad)
        with self.assertRaises(ValueError):
            assemble_evidence(self.corpus, ["missing-unit"])

    def test_stale_cleaned_manifest_is_rejected(self):
        manifest_path = ROOT / "data/cleaned/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["spans.jsonl"] = "stale"
        read_text = Path.read_text

        def changed_manifest(path, *args, **kwargs):
            return json.dumps(manifest) if path == manifest_path else read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=changed_manifest):
            with self.assertRaisesRegex(ValueError, "Cleaned input changed"):
                build_corpus()

    def test_oversized_single_condition_is_split_without_overlap_or_truncation(self):
        text = ("subject to the following conditions and limitations, " * 90
                + "minimum duration of three years and a nominal fee")
        span = SourceSpan(id="test/body", source_key="body", evidence_text=text, language="en",
                          pdf_page=12, bbox_raw=[0, 0, 100, 100], text_origin="mineru", quality_flags=[])
        unit = LogicalUnit(id="test", kind="numbered_note", segments=[
            LanguageRecord(id="test/en", pair_id="test", parallel_id="test/zh-Hant", language="en",
                           title="", text=text, source_span_ids=[span.id], context_span_ids=[]),
            LanguageRecord(id="test/zh-Hant", pair_id="test", parallel_id="test/en", language="zh-Hant",
                           title="", text="條件", source_span_ids=[], context_span_ids=[])], evidence_group="test",
                           source_span_ids=[span.id], context_span_ids=[], requires=[], pages=[12],
                           indexable=True, pairing_status="same_topic_not_equivalence", quality_flags=[])
        ref = SourceSegment(span_id=span.id, start=0, end=len(text), language="en")
        views = _views(unit, {span.id: span}, {span.id: [ref]}, [], [],
                       self.tokenizer, OpenCC("t2s"))
        self.assertGreater(len(views), 1)
        refs = [p for v in views for p in v.source_segments if p.role == "body"]
        self.assertEqual("".join(text[p.start:p.end] for p in refs), text)
        self.assertTrue(all(a.end == b.start for a, b in zip(refs, refs[1:])))
        self.assertTrue(all(v.token_count <= 512 for v in views))
        self.assertIn("nominal fee", views[-1].search_text)


if __name__ == "__main__":
    unittest.main()
