# `tests/eval/` — judge-facing evaluation set

Seven question/answer items that stress the InsureTutor grounded QA agent, built over
[`raw data/source/FLEXI-ULife Prime Saver.pdf`](../../raw%20data/source/FLEXI-ULife%20Prime%20Saver.pdf)
(YF Life 萬通保險, *FLEXI-ULife Prime Saver / 首選靈活萬用壽險計劃*, version `PSP-137-V3-0925B`).

| file | what it is |
|---|---|
| [`ANSWER_KEY.md`](ANSWER_KEY.md) | **Start here.** Human-readable questions, answers, citations, rubrics and traps. |
| [`items.json`](items.json) | Machine-readable source of truth (schema `insuretutor.eval-set/1`). |
| [`test_eval_set.py`](test_eval_set.py) | Contract tests over the *dataset* — not over the tutor. |

```bash
pytest tests/eval -v     # 14 tests, all green
```

## What the seven items cover

| # | id | capability | mode | cites |
|---|----|-----------|------|-------|
| 1 | `q1-two-enhancement-rights` | concept-separation | explain | 7 |
| 2 | `q2-minimum-change-amount-conflict` | citation-integrity | show-conflict | 2 |
| 3 | `q3-bonus-rate-year20` | numeric-precision | explain | 10 |
| 4 | `q4-incremental-death-benefit-netting` | citation-calculation | numeric | 3 |
| 5 | `q5-periodic-withdrawal-eligibility` | edge-case-eligibility | numeric | 4 |
| 6 | `q6-macau-currency-and-lapse` | cross-language | explain | 5 |
| 7 | `q7-scope-refusal-and-version-code` | scope-refusal | refuse | 0 |

Questions are deliberately mixed Simplified / Traditional / English. Answers are anchored to
physical PDF pages (`page_idx + 1`), never to the printed page label or an inferred offset.

## What the contract tests actually enforce

These grade the dataset, not the model — so regenerating `data/cleaned/` fails loudly instead of
letting the eval set silently drift from the corpus it grades against:

- every `unit_id` resolves, and its `pdf_page` is in that unit's `pages`;
- every quote is a **literal substring** of the cleaned unit text (the same standard the runtime
  citation verifier is held to), fragment-wise and whitespace-tolerant;
- **quotes stay Traditional** while questions may be Simplified — a Simplified fold inside a
  quote would make it unciteable;
- footnote-dependent answers reach their note via `requires` / `note_refs`;
- exactly one conflict item, and it must **not** pick a single answer;
- exactly one refusal item, and it carries **no** citations;
- pages are one-based and ≤ 20;
- the set never references `tmp/pages` scratch renders.

## Two constraints to keep in mind when editing

1. **`pdf_page` only.** Printed labels run one behind through the body of the brochure
   (physical 12 → printed "11"). Raw labels are in
   `data/cleaned/manifest.json → printed_page_labels_raw`, all `verified: false`;
   `report.json → verified_printed_pages` holds the one hand-verified page (`{"6": "5"}`).
2. **`raw data/` is frozen.** If you believe the parse is wrong, verify at the codepoint level
   before touching anything — and do not verify Chinese text by reading console output.

## What the contract tests do *not* check

They check the dataset against `data/cleaned/`, which is derived. A quote can be a perfect
substring of the cleaned unit and still misdescribe the printed page. The prose claims in
`ANSWER_KEY.md` about what a page **looks like** — the back-cover version string, the page-6
printed label, page 17's CN/EN currency swap, the June 2 2025 Fortune 500 footnote — were
confirmed by rendering the source PDF and reading the images:

```python
import pypdfium2 as pdfium
doc = pdfium.PdfDocument('raw data/source/FLEXI-ULife Prime Saver.pdf')
doc[19].render(scale=6.0).to_pil().save('tmp/vfy/p20.png')   # 0-based page index
```

`pypdfium2` is not a project dependency; it is only needed for this kind of spot-check. If you
change a claim about what a page shows, re-render and look — do not infer it from the artifact.
