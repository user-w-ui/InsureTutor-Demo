# Judge-facing evaluation set — questions, answers, citations

Ten items for evaluating the InsureTutor QA agent against
[`raw data/source/FLEXI-ULife Prime Saver.pdf`](../../raw%20data/source/FLEXI-ULife%20Prime%20Saver.pdf)
(YF Life 萬通保險, *FLEXI-ULife Prime Saver / 首選靈活萬用壽險計劃*, version `PSP-137-V3-0925B`).

Machine-readable source of truth: [`items.json`](items.json). Contract tests:
[`test_eval_set.py`](test_eval_set.py) — they grade the *dataset*, not the tutor, so a
regenerated corpus fails loudly instead of silently drifting.

## How to read the citations

- **`pdf_page` is the physical PDF page** (`page_idx + 1`) — the only citation anchor.
  Printed page labels run **one behind** the physical page through the body of the brochure
  (physical 8 → printed "7", physical 12 → printed "11", physical 16 → printed "15",
  physical 18 → printed "17"). The raw labels MinerU read are listed in
  `data/cleaned/manifest.json → printed_page_labels_raw`, all marked `verified: false`;
  `printed_page_labels_verified` is `null`, and `data/cleaned/report.json` records the one
  hand-verified page as `verified_printed_pages {"6": "5"}` — MinerU read physical page 6's
  printed label as `"1"` by picking up the section number; the actual bottom label is `5`.
  Cite physical, always.
- The printed page for each citation is given in the tables below as a cross-check, but the
  `pdf_page` is what is authoritative and what the contract tests assert.
- A quote is a **literal substring** of that unit's cleaned `text`. Any quote here can be
  checked with `Ctrl-F` in `data/cleaned/units.jsonl` (fragment-wise, whitespace-tolerant).
- Quotes stay **Traditional**; questions are deliberately mixed Simplified / Traditional /
  English. A Simplified fold inside a quote would make it unciteable.

| # | id | capability | tests |
|---|----|-----------|-------|
| 1 | `q1-two-enhancement-rights` | concept-separation | two near-identical benefit names, footnote-dependent |
| 2 | `q2-minimum-change-amount-conflict` | citation-integrity | a real CN/EN contradiction — must not pick one |
| 3 | `q3-bonus-rate-year20` | numeric-precision | adviser states three wrong things |
| 4 | `q4-incremental-death-benefit-netting` | citation-calculation | which footnote applies (5, not 4) |
| 5 | `q5-periodic-withdrawal-eligibility` | edge-case-eligibility | eligibility gate + a bilingual defect |
| 6 | `q6-macau-currency-and-lapse` | cross-language | Macau currency set, and "unemployment ≠ free premiums" |
| 7 | `q7-scope-refusal-and-version-code` | scope-refusal | must refuse 2025 fulfilment ratio; no fabrication |
| 8 | `q8-grandchild-education-vague` | vague-request-triage | "grandson starts school" — no keywords; reframe to the withdrawal clause |
| 9 | `q9-vague-overreach-uncovered-needs` | scope-refusal | medical / travel / motor: not in this brochure, must not be filled |
| 10 | `q10-nonresident-eligibility-not-in-document` | scope-refusal | "can a non-Hong Kong resident apply?" — the brochure is silent; say so |

**No question tells the tutor where to cite.** Earlier drafts asked for 「引用位置」 outright. The
graded behaviour is that the agent *finds* its own evidence and cites it unprompted, so that demand
now lives only in `rubric` — never in `question`. `test_questions_do_not_tell_the_tutor_where_to_cite`
enforces this: it fails on 「引用」「哪一條附註」「根據第X頁」 and on any question naming one of its own
citation unit ids. The single deliberate exception is Q2 asking for the figures *in all three
currencies* — that is a content requirement, not a pointer at a location.

Q8 is the **vague-input** item: real customer phrasing, deliberately stripped of the retriever's
vocabulary. It tests the path from "no keywords" to the right unit — Q8 must find the one clause
that mentions 子女升學. (The group held two items while 「这个保险怎么样？」 sat beside it; that
question was replaced by Q10, which is short and keyword-free too but has a definite answer the
brochure declines to give.)

Q7, q9 and q10 are **three refusals for three different reasons**, which is the point of having
all three. Q7 refuses a question about figures this edition of *this* product does not publish.
Q9 refuses cover the brochure was never about. Q10 refuses a question that is squarely about this
product — who may take it out — because the document states one qualification and is silent on the
criterion asked. None of the three may be answered from general industry knowledge; each must name
the basis on which it declines.

---

## Q1 — Two enhancement rights with near-identical names

**Capability:** concept-separation · **Languages:** Simplified / Traditional / English

> 保单里好像有两个「增加基本保障额」的权益，名字很像。请告诉我：哪一个会在每个保单年度自动增加、不需要任何健康证明？哪一个需要我结婚或生孩子才能用？这两个权益分别到什么时候失效？如果我用的是「保证可保权益」，每次最多能加多少？一辈子最多能用几次？

**Answer**

Two distinct rights — the whole point of the item is that they get collapsed:

1. **保單增值權益 / Policy Enhancement Option** — *no trigger event*. The Basic Sum Insured
   is automatically increased on each policy anniversary without evidence of insurability
   (electable at application). It terminates on the policy anniversary following the
   Insured's 51st birthday. **It has nothing to do with marriage or childbirth.**
2. **保證可保權益 / Guaranteed Insurability Option** — *triggered* by registering a marriage
   or the birth of a child (note 3 also extends it to legal adoption of a child under 18).
   It can only be exercised **one year after the Effective Date of Coverage**, and terminates
   on the policy anniversary following the Insured's 51st birthday.
3. Limits (note 3): each exercise ≤ **25%** of the Basic Sum Insured *before* exercising;
   across all FLEXI-ULife Prime Saver policies under the same Insured the aggregate increase
   ≤ **US$50,000 / HK$400,000 / MOP400,000**; exercisable **at most twice**.
4. **Presentational difference worth flagging** (see `conflicts` in `items.json`): the page-16
   at-a-glance row words it as *"25% **or** US$50,000/HK$400,000/MOP400,000 (whichever is
   lower)"* — a per-exercise choice — whereas note 3 states 25% per exercise **and** a separate
   aggregate cap across all the Insured's policies. The currency figures agree; the structure
   of the two limits does not.

   Note that this difference exists **in both languages of the page-16 row**, and the Chinese
   is not a translation of the English so much as a restatement — so a bilingual answer should
   quote both:

   - Chinese: 每次增加之基本保障額為行使權益前基本保障額的**25%或**50,000美元/400,000港元/400,000澳門元**(以較低者為準)**；最多可行使權益兩次
   - English: *shall not exceed 25% … or US$50,000/HK$400,000/MOP400,000 (whichever is lower)*
   - note 3, Chinese: 最高為行使權益前基本保障額的25%，而受保人的所有首選靈活萬用壽險計劃保單…合共最高為50,000美元/400,000港元/400,000澳門元 — **no 「以較低者為準」 anywhere**, and the currency cap is scoped to *all* the Insured's policies, not to each exercise.

   Quoting only the English `whichever is lower` and leaving out the Chinese 「以較低者為準」
   loses the bilingual evidence the item asks for.

| unit_id | physical page | printed label | what it establishes |
|---|---|---|---|
| `enhancement` | 6 | 5 | auto-increase, no insurability evidence |
| `note-2` | 12 | 11 | termination at the 51st-birthday anniversary |
| `insurability` | 6 | 5 | marriage / childbirth trigger |
| `note-3` | 12 | 11 | one-year wait, 25%, aggregate cap, max twice (CN + EN) |
| `table-352-row-8` | 16 | 15 | 「以較低者為準」/ "whichever is lower" wording, CN + EN |

**Rubric.** Must separate the two rights and must not attach marriage/childbirth to Policy
Enhancement. Must give *both* terminations, worded as the anniversary **following** the 51st
birthday — "on the 51st birthday" is wrong, and giving a termination age for only one option
is wrong. Must produce all three GIO limits. Bonus for surfacing the at-a-glance vs note-3
difference **with the Chinese 「以較低者為準」 as well as the English "whichever is lower"**.
Citing physical page 5 only supports "both options are offered together" — it carries no terms.

**Traps.** (i) Marriage/childbirth is the *GIO* trigger, not Policy Enhancement's.
(ii) Both terminate at the same event, so a model often gives only one a termination age.
(iii) Confusing the two caps. The source EN of note 3 contains typos — `Efective`, `lega` —
preserved in the artifact; expect them, do not "correct" a quote.

---

## Q2 — The minimum increase/decrease amount (real CN/EN conflict)

**Capability:** citation-integrity · **Languages:** English / Simplified · **Mode:** `show-conflict`

> I need to increase the sum insured. According to the product brochure, what is the minimum amount of each increase/decrease? Please give me the exact figures in all three currencies. 顺便说一下，这份保单要在哪里看这个规定？如果中英文写的不一样，请你直接告诉我哪个才对。

**Answer — both, and refuse to choose**

The same table row (physical page 17, printed "16") disagrees between its two language columns:

- **CN:** 每次更改之最低金額為 5,000美元 / **40,000港元** / **400,000澳門元**
- **EN:** The minimum amount of increase / decrease is US$5,000 / **HK$400,000** / **MOP40,000**

Only the USD figure agrees. **HKD and MOP are swapped between the languages.** This row is
recorded in `data/cleaned/report.json` as `reviewed_source_conflict` with the position
"Neither is selected as authoritative" — so the correct behaviour is to show both and say so,
not to pick one. Physical page 17 visually confirms it; this is a source defect, not a parse
artifact.

| unit_id | physical page | printed label |
|---|---|---|
| `table-354-row-5` | 17 | 16 |

**Rubric.** Both language versions required — one alone is a fail. Must state that HKD/MOP are
*swapped*, not merely "different". Must note USD 5,000 agrees. Must decline to pick a winner
(or say it needs the policy document / underwriting to confirm). Citing any other row on
physical page 17 (minimum sum insured, premium expense charge, administrative charge) does not
count.

**Traps.** A weak model may "resolve" the swap by importing the identical-looking
`HK$400,000/MOP400,000` figures from the page-16 GIO row (`table-352-row-8`). Do not confuse
this row with the withdrawal charge (US$25/HK$200/MOP200, `note-7` physical 12 /
`table-356-row-1` physical 18) — that one is consistent across all three currencies.

---

## Q3 — The adviser's year-20 claim

**Capability:** numeric-precision · **Languages:** Simplified

> 顾问跟我说：这个计划第20个保单年度会派发额外回报，派发率是2.75%，而且基本派息4%会连同额外利息0.25%一起复利滚存。请问他说的对吗？额外回报到底什么时候派发、用哪个比率？另外这个计划有没有什么「保证」的利率？

**Answer — four corrections, and the contrast the item actually tests**

1. **Timing.** Extra Bonus is credited at the end of the **15th** policy year and every
   5 years thereafter (15, 20, 25, 30 …). The adviser is half right — year 20 is a distribution
   year, but the *first* is year 15.
2. **Rate.** 2.75% is the current assumed Extra Bonus rate for the **15th, 20th and 25th**
   years; from the **30th year** onward it is **5.5%**. 2.75% is not year-20-specific.
3. **Interest structure.** Base crediting interest (current assumed **4% p.a.**) and
   retrospective additional interest (current assumed **0.25% p.a.**) are two separate
   arrangements. Base interest is credited monthly at a compound rate; the additional interest
   is calculated from year 1 through 20 and credited **once, at the end of the 20th policy
   year**, then every 5 years thereafter. "4% compounding together with 0.25%" conflates them.
4. **The year-15 / year-20 contrast — two distinct mechanisms, two distinct clocks.** This is
   the point the item is built on, and the one an answer is most likely to gloss.
   Extra *Bonus* (額外回報) starts at the **15th policy anniversary**; retrospective additional
   *interest* (額外利息) accrues from **year 1** and is first credited **at the end of year 20**.
   So "year 20" does belong in this plan — but as the **first crediting of the additional
   interest**, not as the first distribution of the Extra Bonus. The adviser has swapped the two
   clocks. An answer that corrects the year number without ever naming the contrast leaves the
   adviser's actual error — a mechanism mix-up — unaddressed.

   The two clocks, side by side:

   | | starts | first credited | thereafter |
   |---|---|---|---|
   | Extra Bonus (額外回報) | year 15 | end of 15th policy year | every 5 years |
   | Retrospective additional interest (額外利息) | year 1 | end of 20th policy year | every 5 years |
   | Base crediting interest | year 1 | monthly, compound | monthly |

5. **The guarantee.** When a Policy has been in force **15 years or more**, the Account Value
   (including total interest and Extra Bonus credited) is guaranteed to have accumulated to at
   least what a **2.5% p.a.** credited rate would produce. It is an accumulation floor, *not* a
   promised crediting rate.
6. **All of 4%, 0.25%, 2.75%, 5.5% are "current assumed" and not guaranteed** — quoted as of
   the brochure's print date, **January 2022**, and subject to change. The rate table carries its
   own qualifier: **（以派發時適用的額外回報率為準）(subject to the Extra Bonus rate at
   distribution)** — the rate actually applied is the one in force at distribution, not the
   tabulated figure.

| unit_id | physical page | printed label |
|---|---|---|
| `bonus-rate-15-25` | 9 | 8 |
| `extra-bonus-frequency` | 9 | 8 |
| `bonus-rate-30` | 9 | 8 |
| `bonus-rate-disclaimer` | 9 | 8 |
| `base-interest` | 8 | 7 |
| `additional-interest` | 8 | 7 |
| `interest-year20-note` | 8 | 7 |
| `interest-every5-note` | 8 | 7 |
| `table-352-row-6` | 16 | 15 |
| `rate-date-note` | 8 | 7 |

**Rubric.** First distribution at year 15 (not year 20). 5.5% from year 30. 4% and 0.25%
separated, with the 0.25% credited once at the end of year 20. **The year-15 Bonus vs year-20
interest contrast stated explicitly** — that these are independent mechanisms on different
clocks, and that the adviser has swapped them. The 「以派发时适用的额外回报率為準」 qualifier
on the rate table. 2.5% described as an Account Value accumulation floor on policies in force
15+ years. The January 2022 "current assumed, not guaranteed" caveat present. Treating
"4% + 0.25%" as one compounded rate fails even if the arithmetic looks close; so does naming
year 20 as the Extra Bonus's first distribution year.

**Cross-check available to a grader.** The brochure's own worked example (unit `bonus-example`,
physical page 9) uses the formula *Average Monthly Account Value of the preceding 5 years ×
Extra Bonus rate*:

> 於第15個保單週年日派發之「額外回報」
> 過往5年的平均每月賬戶價值 × 額外回報率 = 額外回報 $708,800 × 2.75% = $19,492

Independent check: `(566,000 + 633,000 + 702,000 + 774,000 + 869,000) / 5 = 708,800`;
`708,800 × 0.0275 = 19,492`. The source's own arithmetic is sound — and note that the example
itself is dated **the 15th policy year**, which independently confirms correction (1).

---

## Q4 — Incremental Benefit death benefit

**Capability:** citation-calculation · **Languages:** English / Simplified · **Mode:** `numeric`

> Suppose a Policy is on the Incremental Benefit option. The Basic Sum Insured is US$1,000,000 and the Account Value at the date of death is US$400,000. The insured withdrew US$100,000 eleven months before death. What is the Death Benefit payable? 请给出计算过程，并说明你用哪一条脚注。

**Answer: US$1,150,000**

1. Incremental Benefit death benefit = Account Value **or** Basic Sum Insured + 50% of Account
   Value, **whichever is higher**.
   `1,000,000 + 50% × 400,000 = 1,200,000`
2. **Note 5 applies:** the sum of the Basic Sum Insured and 50% of the Account Value is net of
   **50%** of all withdrawals made in the 12 months preceding death. The withdrawal is 11 months
   before death, so it is in window: `− 50% × 100,000 = − 50,000` → `1,150,000`.
3. Higher of: `max(400,000, 1,150,000) = **1,150,000**`.

**The discriminating step:** Incremental Benefit uses **note 5** (50% netting). Level Benefit
uses **note 4** (full netting) — a model that reaches for the wrong note gets
`1,200,000 − 100,000 = 1,100,000`, and one that skips netting gets `1,200,000`.

| unit_id | physical page | printed label | role |
|---|---|---|---|
| `table-97-row-3` | 7 | 6 | Incremental Benefit formula; declares `requires: note-5` |
| `note-5` | 12 | 11 | 50% netting — the correct note |
| `note-4` | 12 | 11 | full netting — the distractor |

**Rubric.** Final figure US$1,150,000. The `1,000,000 + 200,000 = 1,200,000` step shown. Note 5
correctly identified and applied. The withdrawal explicitly placed inside the 12-month window.
The "whichever is higher" comparison visible. Answer-only responses, or citations to other
page-16 at-a-glance rows, score down.

**Note for the item author:** both the plausible errors — misapplying note 4 and skipping
netting entirely — are partly non-discriminating as *distractors*, because an answer of
`1,200,000` is also what a no-netting model produces. The rubric separates them by requiring
the process, not just the number.

---

## Q5 — Periodic withdrawal eligibility

**Capability:** edge-case-eligibility · **Languages:** Traditional (Cantonese phrasing) / English

> 我份保單生效咗 3 年。我想用「定期提款權益」，每月自動攞錢出嚟，可以嗎？如果可以，每月最少要攞幾多？提款年期有冇最低要求？要唔要交手續費或者提款費用？另外，如果我唔係用定期提款，而係自己每次主動提款，又點計費？

**Answer: not eligible yet — the gate is 10 years**

1. **Eligibility.** The automatic periodic withdrawal option applies only to a Policy in force
   **at least 10 years**. At 3 years, not yet available.
2. **Once eligible:** minimum monthly withdrawal **US$500 / HK$4,000 / MOP4,000**, minimum
   period **one year**; minimum annual withdrawal **US$6,000 / HK$48,000 / MOP48,000**,
   minimum period **three years**.
3. **Charges.** The withdrawal charge is **waived** under the periodic option. A change after
   the application is confirmed attracts a nominal fee.
4. **Ordinary ad-hoc withdrawal:** unlimited frequency, but currently **US$25 / HK$200 /
   MOP200** per withdrawal, not waived.
5. Withdrawals reduce Cash Value accumulation while monthly charges keep being deducted — if
   Cash Value cannot cover them, the Policy can lapse with zero value.

**Source defect to disclose:** the **English** note 6 reads `US$500/HK$/MOP4,000` — the HKD
figure is **missing**. The Chinese carries it (`4,000港元`). The Chinese is the only complete
source for the HKD monthly minimum, and a good answer says so rather than silently repairing it.

| unit_id | physical page | printed label |
|---|---|---|
| `note-6` | 12 | 11 |
| `table-356-row-1` | 18 | 17 |

**Rubric.** The 10-year gate identified *and applied* to reject the 3-year policy. Monthly
minimum and one-year minimum period. Waiver under the periodic option, but a fee for changing
a confirmed arrangement, *versus* US$25/HK$200/MOP200 for ad-hoc withdrawals. Bonus for
disclosing the defective EN note 6.

**Traps.** Answering the annual minimum (US$6,000/HK$48,000/MOP48,000) when the monthly was
asked. Claiming the periodic option still pays the per-withdrawal charge.

---

## Q6 — Macau currency, payment modes, and what "unemployment benefit" really is

**Capability:** cross-language · **Languages:** English / Traditional / Simplified

> For a policy issued in Macau, which currencies can it be denominated in, and what payment modes are available? 另外，如果我中途暂停缴付保费，什么情况下这份保单会失效？还有，市面上都说这个计划有失业保障，是不是我失业就可以一直不用交保费？

**Answer**

1. **Currency.** Policy issued in **Macau**: **US$ / MOP / HK$**. Policy issued in Hong Kong:
   US$ / HK$. The CN and EN columns agree on this row.
2. **Payment mode.** Annual / Semi-annual / Quarterly / Monthly.
3. **Lapse mechanism.** Cash withdrawal, reducing the premium, or skipping premiums reduces
   Cash Value accumulation, while monthly charges remain deductible. **If the Cash Value is not
   sufficient to cover the monthly charges and no premium is paid before the end of the 31-day
   Grace Period from the premium due date, the Policy lapses with zero value.** Note the
   causal chain: the lapse clause on physical page 14 does **not** make "has accumulated Cash
   Value" a precondition for skipping — it makes skipping *erode* the Cash Value, and the
   erosion is what triggers lapse. (A different clause, `skip-premiums` on physical page 10,
   words it as 若需要應急，只要保單內已累積有足夠的現金價值，您可暫停繳付保費 — "When your Policy has
   accumulated a Cash Value, you may skip premium payments to cope with emergencies"; the
   lapse clause is the governing mechanism.)
4. **Unemployment Protection is not free premiums.** If the Policy Owner is made redundant, a
   **Special Grace Period of up to 365 days** is available, during which cover continues in
   full. It is a suspension of payment for up to 365 days, not a waiver. It also applies to the
   **Basic Plan only**, not to supplementary benefits. Distinguish from the ordinary 31-day
   Grace Period.

| unit_id | physical page | printed label |
|---|---|---|
| `table-352-row-14` | 16 | 15 |
| `table-352-row-15` | 16 | 15 |
| `unemployment` | 11 | 10 |
| `note-8` | 12 | 11 |
| `term-and-lapse` | 14 | 13 |

**Rubric.** All three Macau currencies, distinguished from Hong Kong's two. All four payment
modes. Lapse answer containing all three elements: insufficient Cash Value for monthly charges,
the 31-day Grace Period, termination with zero value. Unemployment answered as the 365-day
Special Grace Period with cover continuing, and restricted to the Basic Plan — "you can keep
the policy without paying premiums while unemployed" **fails**. Must not present "already has
Cash Value" as the precondition for skipping.

**Traps.** Carrying Hong Kong's currency set over to a Macau policy. Reading the 365-day figure
as replacing the 31-day period rather than being a separate concession.

---

## Q7 — Version code, and a refusal

**Capability:** scope-refusal · **Languages:** English / Simplified · **Mode:** `refuse`

> Two questions. (a) This brochure is version PS... could you confirm the exact product/version code printed on the brochure? (b) Our clients keep asking about the 2025 fulfilment ratio (履行比率) and the actual crediting interest rate this plan paid out in 2025. Can you give me those numbers from the brochure?

**Answer**

**(a) Answerable.** The version code is **`PSP-137-V3-0925B`**, printed on the back cover
(physical page 20). MinerU types that block as `aside_text`, and the cleaner routes it to
`manifest.json → metadata.version_code` (`block_index 378`, `pdf_page 20`) — it is **not an
index unit**, so a good answer does not claim to have retrieved it from the body index and does
not invent a `unit_id` for it.

> Verified note for graders: the printed glyph and the parsed string are the *same* string.
> Printed position 2 is an **S**, not a 5 — read at 6× zoom after rotation, the glyph shows an
> S's open lower-left counter and top-left terminal, not a 5's flat top bar. Any item built on
> "printed `P5P` vs OCR `PSP`" would manufacture a conflict that does not exist.

**(b) Must refuse — no fabrication.** The brochure contains **no** 2025 fulfilment ratio and
**no** actual crediting / dividend-achievement data. It carries only two *current assumed*
rates — base crediting interest **4% p.a.** and retrospective additional interest **0.25%
p.a.** — and the footnote states these are quoted as of the brochure's print date,
**January 2022**, are not guaranteed, and are subject to change. A rate quoted as of January
2022 cannot answer a question about 2025 actuals.

> **Do not overstate the refusal.** The brochure is *not* a document whose every date is 2022.
> Its back cover (physical page 20) carries a bracketed footnote dated **June 2, 2025** — the
> ranking source for "The Five Largest US Life Insurance Companies": `** The "Five Largest US
> Life Insurance Companies" are ranked according to the results of "Insurance: Life, Health
> (Mutual)" and "Insurance: Life, Health (Stock)" on total revenues for 2024, and based on the
> FORTUNE 500 as published on June 2, 2025.` (unit `company-ranking-note`). A judge who has
> opened the brochure can point straight at that line, so an answer framed as "this brochure
> only contains 2022 material" invites a correction that has nothing to do with the question
> asked.
>
> The narrow, defensible reason is: **the brochure carries no 2025 crediting-rate or
> fulfilment data, and the only rates it does carry are current *assumptions* as at its January
> 2022 print date.** The 2025 date on page 20 is a shareholder-ranking citation and has no
> bearing on policy crediting rates — which is exactly why it does not help answer the question.

**Correct redirection:** the brochure's investment-policy section points readers to the company
website for historical crediting interest rate data; fulfilment ratios / dividend achievement
ratios live on the insurer's dedicated pages, not in a product sales brochure. Give the pointer,
not a number.

**Citation posture.** A pure refusal carries **no citations** — there is no answerable claim to
anchor. The units that establish *why* the brochure cannot answer (b) are recorded separately in
`items.json` under `refusal_grounding` (`rate-date-note`, physical page 8, both languages —
the date and non-guarantee basis — and `company-ranking-note`, physical page 20, the
counter-example that keeps the refusal narrow). Separately, `citations_excluded` documents why
`PSP-137-V3-0925B` is deliberately **not** a citable unit.

**Rubric.** Refusal explicit, with the reason that the brochure does not contain the data. No
invented ratio or rate. The January 2022 "current assumed, not guaranteed" framing used to
explain why the brochure cannot answer. A correct alternative source given — "we don't have it"
alone scores down. Bonus for placing the version code on the back cover via the metadata path.
**Claiming to have found 2025 figures in the brochure scores zero** — that is the fabrication
this item exists to catch. Overstating the refusal as "the brochure contains nothing from 2025"
costs a rubric point: the page-20 Fortune footnote is dated June 2, 2025.

**Traps.** Presenting 4% or 0.25% as the 2025 actual rate. Asserting the printed code differs
from the OCR/manifest string (it does not). Claiming the brochure is entirely a 2022 document —
it is not, and the back cover proves it.

---

## Q8 — "My grandson starts school this year — what should I buy?"

**Capability:** vague-request-triage · **Languages:** Simplified · **Mode:** `explain`

> 我家孙子今年要上学，要投什么保啊？

**Why this item exists.** It has no keyword the retriever can match on: no product name, no
benefit name, no number, no insurance vocabulary beyond 投…保. It is also what a real
prospective customer actually says. Three failure modes are under test — (i) retrieval finds
nothing because there is no lexical bridge; (ii) retrieval finds the *marketing* word
「教育基金」 and stops there; (iii) the agent accepts the customer's framing and produces an
education plan this product is not.

**Correct answer shape.** Re-anchor, then qualify, then hand over the real constraints.

1. **Re-anchor.** "Education" appears in exactly three places, and none of them is a product:
   `front-matter-themes` (physical page 2) lists 「子女成才教育基金Education Funds」 as one of
   five *planning themes*; `withdrawal` (physical page 10) says the periodic withdrawal option
   lets you plan 「各項理財安排（例如子女升學及退休等）」 — the English is explicit:
   *"children's university education funds and retirement expenses"*; and `life-stage-example`
   (physical page 7) first exercises that right at 「兒子大學畢業 University Graduation of Mr.
   Chan's son」. There is no education savings plan, no schooling rider, no education
   endowment anywhere in the brochure.
2. **Qualify.** The 10-year gate in note 6 kills the premise outright: 定期提款權益只適用於
   生效滿10年或以上的保單. A child starting school this year cannot be funded from an option
   that does not open until year 10. The minimums follow — US$500 / HK$4,000 / MOP4,000 a
   month (min. one year) or US$6,000 / HK$48,000 / MOP48,000 a year (min. three years), plus
   the US$25 / HK$200 / MOP200 per-withdrawal charge in note 7.
3. **Hand over the cost.** Withdrawals reduce the Cash Value while the monthly charges keep
   running; if the Cash Value cannot cover them the Policy lapses with **zero** value
   (`cash-value-risk`, fresh on the same physical page 10), and `term-and-lapse` on physical
   page 14 supplies the 31-day grace period.
4. **Decline what is not in the brochure.** Who may own the Policy, the issue-age band for the
   Insured, and whether a grandparent can insure a grandchild are simply **not stated**. Say
   so. Do not invent them, and do not quote a return.

**Citation posture.** Nine citations, led by the one clause that ties the customer's word
「上學」 to this product at all (`withdrawal`, physical page 10). An answer that cites only the
page-2 「教育基金」 theme heading has stopped at the marketing copy — which is precisely what
this item is designed to detect.

**Rubric.** Must reframe (no standalone education plan). Must give at least one hard
constraint from note 6/note 7. Must address the collision between "this year" and the 10-year
gate. Must cite the physical-page-10 子女升學 clause. Must say the ownership/issue-age
questions are uncovered rather than guess. Must not promise any return or attainable amount.

**Traps.** Treating 「教育基金」 as the product's positioning. Answering "yes, withdrawals are
flexible" without the 10-year gate. Inventing policy-ownership rules or a projected education
payout. Answering "the brochure says nothing about education" — it does, in two places.
Citing the page-7 illustration as if it were a benefit term.

---

## Q9 — An open-ended request, padded with needs the brochure never covers

**Capability:** scope-refusal · **Languages:** Simplified · **Mode:** `refuse`

> 我就想买份保险，你看我该买啥？生病了能不能住院报销？出去旅游出事管吗？车撞了赔不赔？

**Why this item exists.** Q7 refuses an answer because the *data* is absent from a document
that is otherwise about the right subject. This one refuses for the opposite reason: three of
the four needs are not what this brochure is about at all. The tempting failure is cross-
document leakage — filling the medical, travel and motor gaps from general insurance common
sense, which is fluent, plausible and entirely unsupported.

**Correct answer shape.**

1. **"What should I buy" is not answerable.** The brochure is a single-product sales leaflet
   (FLEXI-ULife Prime Saver), not advice. Its own disclaimer units and the pervasive
   non-guarantee language say the material is not a recommendation. The answerable version of
   the question is "what does this leaflet cover".
2. **Hospital / medical expenses — not covered.** No hospital benefit, no illness benefit, no
   surgical benefit appears. The brochure's supplementary protections (waiver of premium,
   terminal illness, unemployment, and the like, physical pages 8-11) are not medical cover;
   presenting them as such is the specific error here.
3. **Travel — not covered.** Nothing in the brochure.
4. **Motor — not covered.** Nothing in the brochure.
5. For 2-4, say plainly that they fall outside this brochure's scope, point to the right
   product materials or a licensed adviser, and stop.

**Citation posture.** A refusal cites **nothing**. `refusal_grounding` records the two units
that establish the scope line: the disclaimer units (physical page 17) for the
not-advice point, and `coverage-summary` (physical page 5) whose item list *is* the boundary —
medical, travel and motor are absent from it, and their absence is the evidence.

**Rubric.** Must state this is one universal life product and not advice. Must address all
three uncovered needs — medical, travel, motor — individually; missing one costs a point. No
invented terms, ratios or waiting periods. Must still describe what the leaflet does cover
rather than returning a bare "I can't help". Citations, if any are offered, must land on this
product's own coverage list or disclaimer, never on outside knowledge.

**Traps.** Describing medical reimbursement or any hospital/travel/motor payout. Reframing the
supplementary protections as medical cover. Volunteering an age-and-profile-based product
recommendation. A flat 「无法回答」 with no account of what the leaflet does contain.

---

## Q10 — "Can a non-Hong Kong resident apply?" — in scope, but not in the document

**Capability:** scope-refusal · **Languages:** Simplified · **Mode:** `refuse`

> 我不是香港本地人能投保吗？

**Why this item exists.** Q7 and Q9 refuse questions the brochure *could* not have answered — the
first because the data belongs to a year this edition predates, the second because medical, travel
and motor cover were never what this leaflet is about. Q10 is harder to refuse and therefore the one
that actually catches a fluent guesser: the question is squarely *about this product*, it is phrased
plainly, and there is a large body of plausible-sounding industry knowledge to fill the silence with.
The brochure names exactly one qualification for taking out the policy — issue age — and says nothing
whatsoever about residence, nationality, citizenship, domicile, right of abode, visa or identity
documents. Across all 137 cleaned units there is no sentence on the subject. A tutor that answers
「可以」 or 「不可以」 here is not retrieving; it is recalling.

**Why the obvious neighbours are decoys.** 香港 and 澳門 appear throughout the brochure, and read
carelessly they look like eligibility language:

| looks like | actually is |
|---|---|
| 香港保單:美元/港元　澳門保單:美元/澳門元/港元 (`table-352-row-14`, physical 16) | which **currency** a policy is denominated in, by **place of issue** |
| minimum sum-insured figures split 香港保單 / 澳門保單 (`table-354-row-1`, physical 17) | which **amount floors** apply, by place of issue |
| 保費徵費（只適用於香港） (`levy`, physical 15) | a **levy** on policies issued in Hong Kong, not on applicants |
| two block addresses — 香港北角英皇道…/ 澳門…收回保單 (`cooling-off`, physical 15) | where to **post** a cancellation, not who may buy |
| two servicing contacts — 香港 (852) 2533 5555 / 澳門 (853) 2832 2622 (`disclaimer-zh`, physical 19) | where to **call**, not who may buy |

Every one of these scopes a currency, an amount, a charge or a service point. None of them is a
statement about the applicant. The only row that is shaped like an eligibility rule is the issue-age
row, and it is a trap in the opposite direction: quoting it as the answer asserts a requirement the
document never framed as one.

**Correct answer shape.**

1. **State the silence plainly.** The brochure records no residence, nationality or immigration
   requirement, so it cannot be used to answer this question either way. Not "you can" and not "you
   cannot" — the document does not say.
2. **Name the one qualification it does give.** 投保年齡 `0-75` 歲, and `0-55` 歲 for 特級遞增壽險保障
   / Increasing Benefit Plus — `table-357-row-0`, physical page 18. It speaks only to age.
3. **Defuse the decoys.** Explain that the 香港／澳門 wording marks place of issue and the currency and
   amount schedule that follows from it, and is not a statement about who may apply.
4. **Give the positive basis for declining.** The physical-page-19 disclaimer: the leaflet is
   只供參考 only, 並非保單的一部份 and 未涵蓋保單的所有條款. Eligibility — including any limitation on
   non-residents, and any proof of address or identity — belongs to the policy document and to
   underwriting, which is exactly where the brochure says it is not.
5. **Route it.** A licensed consultant, franchised agent or broker; the hotline the leaflet prints
   (香港 (852) 2533 5555 / 澳門 (853) 2832 2622).
6. Re-asked about a specific person (the grandson from Q8), the same answer holds — age is the only
   stated rule, and residence is still unaddressed.

**Citation posture.** None. The refusal's basis is the *absence* of text, and a citation asserts
presence — quoting the issue-age row would present it as support for an eligibility claim it does not
make. The five `refusal_grounding` entries exist for the grader, not for the answer: they name the
units that show why the refusal is right (`table-357-row-0`, `table-352-row-14`, `levy`,
`disclaimer-zh`, `disclaimer-en`). The answer must not dress them up as citations.

**Rubric.** Must say the brochure is silent on residence/nationality and therefore cannot answer the
question; answering 「可以」 or 「不可以」 outright fails. Must not invoke industry habit or what
insurers "usually" require — that is the specific failure this item is built to catch. Should cite the
issue-age row as the sole stated qualification while making clear it does not address residence.
Should read the 香港／澳門 split as place-of-issue currency scoping, not as cross-border eligibility.
Should use the page-19 disclaimer as the affirmative reason the question falls outside the leaflet,
and should end with a route to a licensed source rather than a bare 「不知道」.

**Traps.** 「可以投保，本产品不限居留地」 (nothing in the document says this). 「不可以，必须为香港居民」
(equally unsupported). Quoting 0-75 歲 as if it answered the question. Reading the Hong Kong / Macau
policy split, or the two addresses, as evidence of cross-border eligibility. Filling the gap with
「一般来说非居民也可以买，只要……」 or 「香港公司通常会要求香港身分证」. A flat 「不知道」 with no account of
what the leaflet does and does not contain.

---

## Two source facts this set deliberately does *not* use

Both were checked and found to be **non-issues**; they are recorded here so they are not
re-proposed as items:

- **Physical page 11 heading.** The English heading prints **"Unemployment Protection"** —
  correctly spelled. There is no "Unemployement" typo. (Typos do exist elsewhere, and a
  spelling-based item would have to target one of these: `ofers` for "offers"
  (`waiver-of-premium`, physical 11), `diferent` (`life-stage-example`, physical 7), `afected`
  (`investment-performance`, physical 13), `suficient` (`cash-value-risk` physical 10 and
  `term-and-lapse` physical 14), plus `Efective` / `lega` in `note-3`.)
- **Physical page 6 printed label.** The bottom-left label is a clear single glyph **5**,
  confirming `verified_printed_pages {"6": "5"}`. MinerU's raw label `"1"` is the misread. The
  offset is real and consistent (physical − 1 through the body), and is why every citation in
  this set is given as a physical page.
