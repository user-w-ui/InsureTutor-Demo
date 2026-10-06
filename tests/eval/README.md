# `tests/eval/` — judge-facing evaluation set

Ten question/answer items that stress the InsureTutor grounded QA agent, built over
[`raw data/source/FLEXI-ULife Prime Saver.pdf`](../../raw%20data/source/FLEXI-ULife%20Prime%20Saver.pdf)
(YF Life 萬通保險, *FLEXI-ULife Prime Saver / 首選靈活萬用壽險計劃*, version `PSP-137-V3-0925B`).

| file | what it is |
|---|---|
| [`items.json`](items.json) | **The only source of truth** (schema `insuretutor.eval-set/2`): questions, reference answers, evidence, rubrics and traps. |
| [`test_eval_set.py`](test_eval_set.py) | Contract tests over the *dataset* — not over the tutor. |
| [`judge-prompt.md`](judge-prompt.md) | Fixed prompt for the offline rubric judge (a Sonnet subagent); only file paths are filled in. |
| [`chat-scenarios.json`](chat-scenarios.json) | Additional multilingual, multi-turn and misuse scenarios for the chat CLI. |

```powershell
uv run --locked --extra agent --extra dev python -m pytest tests/eval -v
```

Real retrieval and chat evaluation commands are in the [development guide](../../docs/development.md#cli-and-evaluation).
Fixtures stay outside runtime prompts and indexes. The rubric evaluates meaning and
completeness; runtime validation checks only structure and submitted citation provenance.

## What the ten items cover

| # | id | capability | mode | required / supporting |
|---|----|-----------|------|-------|
| 1 | `q1-two-enhancement-rights` | concept-separation | explain | 4 / 2 |
| 2 | `q2-minimum-change-amount-conflict` | citation-integrity | show-conflict | 1 / 3 |
| 3 | `q3-bonus-rate-year20` | numeric-precision | explain | 9 / 9 |
| 4 | `q4-incremental-death-benefit-netting` | citation-calculation | numeric | 2 / 3 |
| 5 | `q5-periodic-withdrawal-eligibility` | edge-case-eligibility | numeric | 2 / 5 |
| 6 | `q6-macau-currency-and-lapse` | cross-language | explain | 5 / 6 |
| 7 | `q7-2025-rates-not-in-brochure` | scope-refusal | refuse | 0 / 10 |
| 8 | `q8-grandchild-education-vague` | vague-request-triage | explain | 2 / 7 |
| 9 | `q9-vague-overreach-uncovered-needs` | scope-refusal | refuse | 0 / 10 |
| 10 | `q10-nonresident-eligibility-not-in-document` | scope-refusal | refuse | 0 / 6 |

Questions are deliberately mixed Simplified / Traditional / English. Each item's
`scenario_note` states what it tests. A few design points:

- **No question tells the tutor where to cite.** The graded behaviour is that the agent finds
  its own evidence, so citation demands live only in `rubric`. The one deliberate exception is
  q2 asking for the figures *in all three currencies*: a content requirement, not a location.
- **q8 is the vague-input item.** It reads like a real customer, with no product, benefit or
  figure named. Its only bridge into the corpus is the physical-page-10 withdrawal clause that
  names 子女升學 / *children's university education funds*. It may end with one clarification
  question, but the key facts (10-year threshold, uncovered ownership questions) must be given.
- **q7, q9 and q10 are three refusals for three different reasons.** q7 asks for 2025 figures
  this brochure does not publish; q9 asks about medical, travel and motor cover it was never
  about; q10 asks who may take out *this* product, and the brochure states only an issue age
  (0-75, physical page 18). `香港 / 澳門` throughout the brochure scopes currency, minimum
  amounts and the levy by place of issue, never eligibility.
- **q3 is half right on purpose.** The adviser's "year 20 pays a 2.75% extra bonus" matches the
  brochure; "4% compounds together with 0.25%" does not. The answer must say which is which.

## Item format

Every item has the same fields in the same order (enforced by
`test_schema_and_fixed_field_order`):

| field | meaning |
|---|---|
| `id`, `capability`, `answer_mode` | `answer_mode` is `explain`, `numeric`, `show-conflict` or `refuse` |
| `question`, `question_languages` | the user turn, exactly as sent to the tutor |
| `scenario_note` | what the item tests and why the trap is a trap |
| `accepted_statuses` | tutor statuses that count as the right outcome |
| `expected_answer` | Simplified Chinese; first line `结论：…`, then numbered points citing physical pages |
| `evidence.required` | units a complete answer must show; drives citation recall (empty for refusals) |
| `evidence.supporting` | other relevant units (contrast notes, at-a-glance rows, context, refusal basis) |
| `rubric`, `veto_rubric`, `bonus_rubric` | one checkable point per line; bonus lines start with `加分项：` |
| `wrong_answers` | typical mistakes the judge should penalise |
| `source_issues` | CN/EN conflicts, presentational differences and defects in the brochure itself |

An evidence entry is `{unit_id, pdf_page, quotes: {"zh-Hant"?, "en"?}, note}`. Traps (for example
note 4 in q4, or the issue-age row in q10) are listed as `supporting` with a `note` explaining
how they may and may not be used; they are never `required`.

Reference answers state brochure facts and expected behaviour only: no unit numbering, parser
block types, manifest paths or review labels, which the tutor never sees
(`test_answers_carry_no_pipeline_internals`).

## Scoring fields

Offline quality scoring (`python -m insuretutor.evaluation`, see the
[development guide](../../docs/development.md#cli-and-evaluation)) reads:

- `accepted_statuses` — a refusal may also answer or clarify around an explicit `boundary`
  claim; a degraded turn (`reason` set) is wrong. Only the vague-request item (q8) adds
  `clarification`.
- `evidence.required` — citation recall: required units among the displayed citations.
- `evidence.required` ∪ `evidence.supporting` — after note closure, the relevant set for
  citation precision over the units the model selected.
- `veto_rubric` — one-based rubric lines scored only pass/fail; a failed veto line zeroes the item.
- `bonus_rubric` — scored but excluded from the item score and reported separately.

## What the contract tests enforce

These grade the dataset, not the model — so regenerating `data/cleaned/` fails loudly instead of
letting the eval set silently drift from the corpus it grades against:

- the schema, field set and field order are fixed; every evidence entry quotes the source;
- every `unit_id` resolves, its `pdf_page` is in that unit's `pages` (one-based, ≤ 20), and a unit
  is listed once per item;
- every quote is a **literal substring** of the cleaned record in its language, fragment-wise and
  whitespace-tolerant; **Chinese quotes stay Traditional**, while questions may be Simplified;
- `tests/retrieval_cases.json` core targets are all listed as evidence of the same item;
- exactly one conflict item, with a `language_conflict` on a unit recorded in `report.json` and
  quoted in both languages;
- all three refusals have no required evidence but do have supporting evidence;
- reference answers, scenario notes and rubrics carry no pipeline internals;
- no question points the tutor at a citation or names one of its evidence unit ids;
- the vague-question item stays under 60 characters and leaks none of the corpus's own
  terminology (「定期提款」「現金價值」「USD」…);
- `accepted_statuses` match `answer_mode`, and veto/bonus lines exist and never overlap;
- the set never references `tmp/pages` scratch renders.

## Two constraints to keep in mind when editing

1. **`pdf_page` only.** Printed labels run one behind through the body of the brochure
   (physical 12 → printed "11"). Raw labels are in
   `data/cleaned/manifest.json → printed_page_labels_raw`, all `verified: false`;
   `report.json → verified_printed_pages` holds the one hand-verified page (`{"6": "5"}`):
   MinerU read physical page 6's label as `"1"`, but the printed glyph is a clear `5`.
2. **`raw data/` is frozen.** If you believe the parse is wrong, verify at the codepoint level
   before touching anything — and do not verify Chinese text by reading console output.

## What the contract tests do *not* check

They check the dataset against `data/cleaned/`, which is derived. A quote can be a perfect
substring of the cleaned unit and still misdescribe the printed page. These claims about what a
page **looks like** were confirmed by rendering the source PDF and reading the images:

- the back-cover version string reads `PSP-137-V3-0925B` (not `P5P…`); it lives only in
  manifest metadata, not in any retrievable unit, so no item asks for it;
- physical page 17's increase/decrease row really swaps the HK$ and MOP figures between CN and EN;
- the page-20 `**` footnote really dates the Fortune 500 ranking 2 June 2025;
- the page-11 English heading is correctly spelled "Unemployment Protection". Real typos exist
  elsewhere (`ofers`, `diferent`, `afected`, `suficient`, `Efective`, `lega`) and are kept
  verbatim in quotes.

```python
import pypdfium2 as pdfium
doc = pdfium.PdfDocument('raw data/source/FLEXI-ULife Prime Saver.pdf')
doc[19].render(scale=6.0).to_pil().save('tmp/vfy/p20.png')   # 0-based page index
```

`pypdfium2` is not a project dependency; it is only needed for this kind of spot-check. If you
change a claim about what a page shows, re-render and look — do not infer it from the artifact.
