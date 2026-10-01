# `tests/eval/` — judge-facing evaluation set

Ten question/answer items that stress the InsureTutor grounded QA agent, built over
[`raw data/source/FLEXI-ULife Prime Saver.pdf`](../../raw%20data/source/FLEXI-ULife%20Prime%20Saver.pdf)
(YF Life 萬通保險, *FLEXI-ULife Prime Saver / 首選靈活萬用壽險計劃*, version `PSP-137-V3-0925B`).

| file | what it is |
|---|---|
| [`ANSWER_KEY.md`](ANSWER_KEY.md) | **Start here.** Human-readable questions, answers, citations, rubrics and traps. |
| [`items.json`](items.json) | Machine-readable source of truth (schema `insuretutor.eval-set/1`). |
| [`test_eval_set.py`](test_eval_set.py) | Contract tests over the *dataset* — not over the tutor. |
| [`chat-scenarios.json`](chat-scenarios.json) | Additional multilingual, multi-turn and misuse scenarios for the chat CLI. |

```powershell
uv run --locked --extra agent --extra dev python -m pytest tests/eval -v
```

Real retrieval and chat evaluation commands are in the [README](../../README.md#cli-and-evaluation).
Fixtures stay outside runtime prompts and indexes. The rubric evaluates meaning and
completeness; runtime validation checks only structure and submitted citation provenance.

## What the ten items cover

| # | id | capability | mode | cites |
|---|----|-----------|------|-------|
| 1 | `q1-two-enhancement-rights` | concept-separation | explain | 7 |
| 2 | `q2-minimum-change-amount-conflict` | citation-integrity | show-conflict | 2 |
| 3 | `q3-bonus-rate-year20` | numeric-precision | explain | 10 |
| 4 | `q4-incremental-death-benefit-netting` | citation-calculation | numeric | 3 |
| 5 | `q5-periodic-withdrawal-eligibility` | edge-case-eligibility | numeric | 4 |
| 6 | `q6-macau-currency-and-lapse` | cross-language | explain | 5 |
| 7 | `q7-scope-refusal-and-version-code` | scope-refusal | refuse | 0 (+3 grounding) |
| 8 | `q8-grandchild-education-vague` | vague-request-triage | explain | 9 |
| 9 | `q9-vague-overreach-uncovered-needs` | scope-refusal | refuse | 0 (+2 grounding) |
| 10 | `q10-nonresident-eligibility-not-in-document` | scope-refusal | refuse | 0 (+5 grounding) |

Questions are deliberately mixed Simplified / Traditional / English. Answers are anchored to
physical PDF pages (`page_idx + 1`), never to the printed page label or an inferred offset.

**No question tells the tutor where to cite.** Earlier drafts asked for "引用位置" outright;
the graded behaviour is that the agent *finds* its own evidence, so the demand now lives only in
`rubric`, never in `question`. `test_questions_do_not_tell_the_tutor_where_to_cite` holds that
line — it fails on 「引用」「哪一條附註」「根據第X頁」 and on any question that names one of its own
citation unit ids. The one deliberate exception is q2 asking for the figures *in all three
currencies*: that is a content requirement, not a pointer at a location. A companion test,
`test_answer_key_blockquote_matches_items_json_question`, requires every question to appear
verbatim as a blockquote in `ANSWER_KEY.md` — the two files are one question in two views, and
nothing kept them in step until an edit to one and not the other was caught by an audit.

**Q8 is the vague-input item.** It reads like a real customer — no product name, no benefit
name, no figure, nothing the retriever can match lexically. It has a single bridge into the
corpus: the physical-page-10 withdrawal clause that names 子女升學 / *children's university
education funds*. A separate contract test (`test_vague_items_read_like_a_real_user`) keeps it
vague — if a future edit names an option or a currency figure in the question, the test fails,
because the item would no longer be testing retrieval.

**Q7, q9 and q10 are three refusals for three different reasons**, and the difference is the
point. Q7 refuses a question about figures this edition of *this* product does not publish (2025
crediting rates). Q9 refuses three lines of cover the brochure was never about (medical, travel,
motor). Q10 refuses a question that is squarely about this product — who may take it out — because
the brochure states exactly one qualification (issue age 0-75, 0-55 for Increasing Benefit Plus,
physical page 18) and says nothing whatever about residence, nationality or immigration status.
The nearest-looking text is a decoy: 香港 / 澳門 throughout the brochure scopes *currency, minimum
amounts and the premium levy by place of issue*, never eligibility. Each refusal therefore carries
no citations but does carry `refusal_grounding` — the units a grader reads to see why the refusal
is right — and each must name its basis rather than shrug.

## What the contract tests actually enforce

These grade the dataset, not the model — so regenerating `data/cleaned/` fails loudly instead of
letting the eval set silently drift from the corpus it grades against:

- every `unit_id` resolves, and its `pdf_page` is in that unit's `pages`;
- every fixture quote is a **literal substring** of a cleaned language record,
  fragment-wise and whitespace-tolerant; runtime quotes instead come directly
  from the registered source span's `evidence_text`;
- **Chinese quotes stay Traditional** and English quotes stay English, while questions may be Simplified — a Simplified fold inside a
  quote would make it unciteable;
- footnote-dependent answers reach their note via `requires` / `note_refs`;
- exactly one conflict item, and it must **not** pick a single answer;
- all three refusal items carry **no** citations and must set `must_not_fabricate`, and each must
  supply `refusal_grounding` — a refusal that cites nothing still has to state what it stands on;
- every `refusal_grounding` unit id resolves, its `pdf_page` is in that unit's `pages`, and its
  quote is a literal substring by the same fragment-wise rule the citations get (added after q9
  shipped pointing at physical page 17 for a unit that lives on 19);
- no question points the tutor at a citation — no 「引用」「哪一條附註」「根據第X頁」, and no question
  that names one of its own citation unit ids;
- every question also appears verbatim as a blockquote in `ANSWER_KEY.md`, so the human-readable key
  cannot drift from `items.json`;
- the vague-question items stay under 60 characters and leak none of the corpus's own terminology
  (「定期提款」「現金價值」「USD」…) — an item that names the option has stopped testing retrieval;
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
