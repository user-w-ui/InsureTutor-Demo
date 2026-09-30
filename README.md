# InsureTutor

An AI tutor over a Hong Kong universal-life insurance brochure — grounded chat with
verifiable citations, plus guardrails against misuse.

Take-home task for the NUS Asian Institute of Digital Finance (AIDF) AI Full Stack
Engineer internship. See [`docs/task-spec.md`](docs/task-spec.md) for the original brief.

**For reviewers:** Start with the [technical architecture (中文)](docs/architecture.zh-CN.md)
for the system diagram, module boundaries, request flow, retrieval, and safety design.
Data contracts, source discrepancies, and implementation reminders are in
[implementation notes (中文)](docs/implementation-notes.zh-CN.md).

**Source document:** `FLEXI-ULife Prime Saver.pdf` — 20-page bilingual
(Traditional Chinese / English) product brochure, YF Life 萬通保險.
**Domain language:** Traditional Chinese + English, each retained as original evidence.
Neither language is silently preferred when the brochure disagrees with itself.

## Cleaned data and runtime corpus (implemented)

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
the confirmed source conflict, and finite PDF-verified text corrections with source
blocks and physical pages. `units.jsonl` contains clean fragments for the next chunking
step; `spans.jsonl` provides `evidence_text` and its `text_origin` for citation checks.
Corrected bilingual views separate language, title, and body. The seven known text
issues and both formulas are resolved; the page 17 source conflict remains explicit.
Use only indexable units and follow their `requires` links before answering.
The cleaner retains original extraction text for provenance and marks PDF-verified
corrections; it does not certify the entire brochure or translate it into Simplified Chinese.

### Build the runtime corpus

```powershell
python -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
python -m insuretutor.corpus
python -m pytest -q
```

[`data/corpus.json`](data/corpus.json) preserves all 137 logical units and 458 source
spans, with 275 retrieval children: 137 Chinese and 138 English. Every unit has both
language views; the longer English exclusion list needs two children. English views
contain no Chinese. Chinese search text uses OpenCC Simplified forms; citations keep
the original `evidence_text`, physical PDF page and raw bbox.

[`corpus-rules.json`](data/corpus-rules.json) records reviewed language boundaries,
table/context associations, and the explicitly paired standalone disclaimers.
Footnote links and source conflicts remain owned by the cleaner. The pinned E5
[tokenizer](data/tokenizer/README.md) is included for offline length checks; model
weights and embedding generation are deferred to Step 2.

The two data entry points are in [`insuretutor.corpus`](src/insuretutor/corpus.py):
`build_corpus() -> Corpus` and `assemble_evidence(corpus, unit_ids) -> EvidenceBundle`.
Assembly restores full parents, follows required notes, adds headers/context and
retains both conflict sources. Rebuilds are byte-identical, and tests use no model API.

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

A single Docker container serves a FastAPI backend and static chat UI. It loads a
committed corpus and precomputed vectors for BM25 + NumPy hybrid retrieval.
Application code resolves the query, retrieves clauses and required notes, then passes structured evidence to a
tool-free OpenAI Agents SDK agent. The server validates the draft and constructs
PDF citations before returning the answer. Without an LLM, it returns labelled
source excerpts. Query embeddings run locally on CPU with multilingual-e5-small
through FastEmbed; the model and tokenizer are bundled in the Docker image.

See the [technical architecture](docs/architecture.zh-CN.md) for the complete design;
[data and implementation details](docs/implementation-notes.zh-CN.md) are maintained
separately. Cleaning, corpus construction and evidence assembly are implemented;
retrieval and the conversation runtime remain planned.

---

## Layout

```
raw data/
  mineru-official/           Verbatim MinerU output — never edited by hand
    content/                 Markdown + JSON + images/ (all three as siblings)
    MANIFEST.md              Provenance: tool, version, params, checksums, date
src/insuretutor/
  corpus.py                  Corpus models, offline builder, evidence assembly
  ingest/                    cleaning (build-time only)
  retrieval/                 Lexical index + required-link completion
  guardrails/                Refusal & scope policy
  tutor.py                   Full request lifecycle (to add)
  generation.py              Tool-free Agents SDK adapter (to add)
  api/                       FastAPI app
data/
  cleaning-rules.json        Source-pinned corrections, structure & evidence links
  cleaned/                   Generated clean fragments and provenance (implemented)
  corpus-rules.json          Reviewed language boundaries and context associations
  corpus.json                Runtime artifact (implemented)
  tokenizer/                 Pinned E5 tokenizer only, no embedding weights
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
- [x] Nine-table / ten-note map and offline cleaner implemented
- [ ] Bilingual glossary drafted
- [x] Cleaned fragments and reviewed metadata integrated into `corpus.json`
- [ ] Retrieval + citation
- [ ] Guardrails
- [ ] API + frontend
- [ ] Docker

## Credentials

No API keys in this repository. `.env` and `raw data/**/MANIFEST.local.*` are gitignored.
The runtime LLM key is supplied by whoever runs the container.
