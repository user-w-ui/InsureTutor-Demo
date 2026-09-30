# InsureTutor

An AI tutor over a Hong Kong universal-life insurance brochure — grounded chat with
verifiable citations, plus guardrails against misuse.

Take-home task for the NUS Asian Institute of Digital Finance (AIDF) AI Full Stack
Engineer internship. See [`docs/task-spec.md`](docs/task-spec.md) for the original brief.

**Source document:** `FLEXI-ULife Prime Saver.pdf` — 20-page bilingual
(Traditional Chinese / English) product brochure, YF Life 萬通保險.
**Domain language:** Traditional Chinese + English, each retained as original evidence.
Neither language is silently preferred when the brochure disagrees with itself.

## Cleaned data (implemented)

The offline cleaner writes separately to [`data/cleaned/`](data/cleaned/README.md),
leaving `raw data/` unchanged. Start with the [readable preview](data/cleaned/preview.md),
[quality report](data/cleaned/report.json), and [table/note map](docs/data-cleaning-map.md).
The remaining application architecture below is a proposal, not an implemented runtime.

From the repository root, using Python 3.11 or newer (no third-party dependencies
are needed for cleaning or its tests):

```powershell
$env:PYTHONPATH = "src"
python -m insuretutor.ingest.clean
python -m unittest discover -s tests -v
```

The source-pinned [`data/cleaning-rules.json`](data/cleaning-rules.json) declares exact
reference markers, bilingual topic groups, table structure, required evidence, and
the confirmed source conflict. It does not supply replacement source text.
`units.jsonl` is the retrieval input; `spans.jsonl` retains original citation anchors.
Use only indexable units and follow their `requires` links before answering.
The cleaner preserves damaged text with explicit flags; it does not certify the
entire brochure or translate the corpus into Simplified Chinese.

---

## Why this is harder than "just a RAG"

The document is small (39k characters) but adversarial for retrieval:

| Property | Consequence for the design |
|---|---|
| Bilingual, page-interleaved | Every fact exists twice. Naive chunking retrieves both and doubles the context for no gain. |
| Footnote-numbered semantics | `附註 3` / `Note 3` carries the actual limits (25% cap, 51st birthday, 2 exercises). A footnote chunked away from its referent is a **wrong answer**, not an incomplete one. |
| Dense numeric conditions | `500美元/4,000港元/4,000澳門元`, `2.5% p.a.`, `15th policy year` — exact-match matters more than fuzzy semantics. |
| Non-guaranteed vs guaranteed | `保證` vs `現時假設` is the single most important distinction in the document; conflating them is a compliance-grade error. |
| Misuse surface | A financial product invites "should I buy this?" and "guarantee me 4%" — both must be refused *with a cited reason*, not a generic refusal. |

So the real work is **chunking on semantic anchors, hybrid retrieval, and
citation-verified answering** — not the chat loop.

---

## Architecture

### Build time vs run time

The parse is **one-time and deterministic**. The committed artifact — not the PDF —
is what the container reads.

```
PDF ──(one-time, offline)──► raw data/ ──(one-time)──► data/corpus.json ──► committed
                                  ▲                                              │
                        data/curation.json                                       │
                        (reviewed links)            docker run ─────────────────┘
                                                          │
                                             retrieval + citation + guardrails
```

The parse is frozen, but the corpus is not a raw copy of it: `build_corpus(raw, curation)`
is a pure function of two committed inputs, so it re-runs to a byte-identical artifact.
`data/curation.json` is the only hand-authored input — it declares the note links and
reviewed conflicts that the parse alone cannot prove, and never alters source text.

Rationale: the grader gets a container that boots in seconds with no network
dependency for ingestion, and the citation anchors are **frozen** — reproducible,
diffable, and not subject to a re-parse silently shifting page numbers.

### Pipeline

| Stage | What it does | Where |
|---|---|---|
| 1. Parse | PDF → Markdown + JSON + images | `raw data/mineru-official/` (MinerU official API) |
| 2. Normalize | Traditional → Simplified for **indexing only**; original retained for display | `src/insuretutor/ingest/` |
| 3. Chunk | Semantic-anchor chunking (clause / footnote / condition as indivisible units) | `src/insuretutor/ingest/` |
| 4. Index | Hybrid BM25 + vector, in-process, no external service | `src/insuretutor/retrieval/` |
| 5. Answer | Retrieval → grounded generation → citation verification | `src/insuretutor/api/` |
| 6. Guard | Refusal / scope / advice-boundary checks | `src/insuretutor/guardrails/` |

### Retrieval decisions

- **Semantic-anchor chunking, not fixed windows.** A chunk is a clause, a numbered
  footnote, or a self-contained condition table — never split mid-condition.
- **Traditional → Simplified is one-way, indexing-side only.** OpenCC `t2s` for the
  search index. The displayed citation always shows the original Traditional text,
  because that is what the source document actually says and what a human checking
  the citation will look up. Never convert Simplified back to Traditional for display.
- **Hybrid BM25 + vector.** BM25 wins on `2.5%`, `51歲`, `400,000`; the vector side
  wins on paraphrase ("what happens if I stop paying" → 暫停繳付保費 / Skip Premium Payments).
- **Bilingual pairing.** CN and EN segments of the same fact are grouped into one
  chunk with a single anchor, so a retrieval hit yields both languages rather than
  competing duplicates.

### Answer modes

Two modes behind one interface — the tutor degrades instead of breaking:

- **LLM mode** — the user supplies an OpenAI-compatible key at run time. Grounded
  generation over retrieved context.
- **Offline / extractive mode** — no key. Returns retrieved passages with citations
  and no synthesis. Still useful, still correct, still cited.

---

## Layout

```
raw data/
  mineru-official/           Verbatim MinerU output — never edited by hand
    content/                 Markdown + JSON + images/ (all three as siblings)
    MANIFEST.md              Provenance: tool, version, params, checksums, date
src/insuretutor/
  ingest/                    raw artifacts + curation → corpus.json (build-time only)
  retrieval/                 Lexical index + required-link completion
  guardrails/                Refusal & scope policy
  tutor.py                   Full request lifecycle (to add)
  api/                       FastAPI app
data/
  curation.json              Hand-authored note links & reviewed conflicts — committed
  corpus.json                Generated artifact — committed
frontend/                    Single-page chat UI
docs/                        Task spec, architecture, data provenance
docker/                      Dockerfile + compose
tests/                       Includes adversarial guardrail cases
```

## Reproducing the parse

The parse is committed, so this is optional. It requires a mineru.net token
(`MINERU_TOKEN`), which is **never** stored in this repo.

```powershell
mineru-open-api extract 'FLEXI-ULife Prime Saver.pdf' `
  -o 'raw data/mineru-official' -f md,json --timeout 1800 -v
```

Homepage upload of a 7.6 MB PDF takes ~4 minutes; cloud parsing ~2 minutes.
`--timeout 1800` is required — the default 300 s fails on upload, not on parsing.
See [`docs/data-provenance.md`](docs/data-provenance.md) for the full log.

## Status

- [x] Source PDF analysed, parse path determined
- [x] Official-API parse verified (380 blocks, 20 pages, 9 tables, 72 headings, 42 images)
- [ ] Nine-table / ten-note map reviewed (**blocks ingest**)
- [ ] Bilingual glossary drafted (**blocks ingest**)
- [ ] `curation.json` written
- [ ] `corpus.json` generated
- [ ] Retrieval + citation
- [ ] Guardrails
- [ ] API + frontend
- [ ] Docker

## Credentials

No API keys in this repository. `.env` and `raw data/**/MANIFEST.local.*` are gitignored.
The runtime LLM key is supplied by whoever runs the container.
