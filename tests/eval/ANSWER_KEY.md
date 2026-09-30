# Judge-facing evaluation set — questions, answers, citations

Seven items for evaluating the InsureTutor QA agent against
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
