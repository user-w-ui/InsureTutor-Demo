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

## Install dependencies

Use **uv** and Python **3.12**. From the repository root:

```powershell
uv sync --locked --extra agent --extra dev
```

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

## Cleaned data and runtime corpus (implemented)

The offline cleaner writes separately to [`data/cleaned/`](data/cleaned/README.md),
leaving `raw data/` unchanged. Start with the [readable preview](data/cleaned/preview.md),
[quality report](data/cleaned/report.json), and [table/note map](docs/data-cleaning-map.md).
Local retrieval is implemented; the chat API, generation and guardrails remain planned.

From the repository root, using Python 3.11 or newer (no third-party dependencies
are needed for cleaning or its tests):

```powershell
$env:PYTHONPATH = "src"
python -m insuretutor.ingest.clean
python -m unittest discover -s tests -p "test_cleaning.py" -v
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
uv run --locked --extra agent --extra dev python -m insuretutor.corpus
uv run --locked --extra agent --extra dev python -m pytest -q
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
weights are prepared separately by the Step 2 command below.

The two data entry points are in [`insuretutor.corpus`](src/insuretutor/corpus.py):
`build_corpus() -> Corpus` and `assemble_evidence(corpus, unit_ids) -> EvidenceBundle`.
Assembly restores full parents, follows required notes, adds headers/context and
retains both conflict sources. Rebuilds are byte-identical, and tests use no model API.

### Run local retrieval (implemented)

```powershell
# This is the only retrieval command that downloads files (470 MB FP32 model).
uv run --locked --extra agent --extra dev python -m insuretutor.retrieval prepare-model
# Vectors are committed; rebuild explicitly only when corpus / encoding changes.
uv run --locked --extra agent --extra dev python -m insuretutor.retrieval build-index
uv run --locked --extra agent --extra dev python -m insuretutor.retrieval query "保證可保權益最多可行使幾次？" --output tmp/query.json
uv run --locked --extra agent --extra dev python -m insuretutor.retrieval evaluate
uv run --locked --extra agent --extra dev python -m pytest -q
```

After preparation, query, indexing and evaluation require no network or model API.
The CLI's evaluation blocks outbound socket connections during model initialization
and inference. A missing, damaged or mismatched artifact fails explicitly.
Model files live in ignored `models/multilingual-e5-small/`; the committed
[manifest and vectors](data/retrieval/README.md) pin corpus, ordered views, assets and encoding.
Defaults: 2 CPU threads; top 12 units per channel; equal RRF with constant 60;
up to 8 direct hits and 12,000 deduplicated source characters. Automatically completed
notes use no direct-hit slots. Responses are complete evidence bundles with original
text, physical PDF pages and bounding boxes; this CLI does not generate answers.

### Read-only agent tool (adapter implemented; conversation loop next)

Create a per-turn `EvidenceSearchSession`, then call `await session.initialize(question)`
once with the full original question before starting the agent. Include the result's
`to_agent_json()` in the model input as structured, untrusted evidence.
`make_search_evidence_tool(session)` wraps the same Retriever as an SDK `function_tool`
and requires initial retrieval to have completed. The agent will inspect initial
evidence, answer directly when sufficient, or choose focused supplemental searches.
Each result is complete; results are not manually ranked or merged across searches.
Initial and supplemental evidence share the citation registry and 12,000 unique source
characters. The default 6 searches include 1 initial search and up to 5 tool calls.
Schema and actual SDK tool execution are tested without a model API; the Runner
loop, answer generation and safety validation are the next step.
See [implementation notes](docs/implementation-notes.zh-CN.md) for measured recall,
latency and remaining retrieval gaps.

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
The server first retrieves the full original question and provides structured evidence
to one OpenAI Agents SDK agent, which may supplement it through a read-only search tool.
The server controls shared retrieval budgets, preserves required
notes, records citable evidence and validates the draft. It constructs
PDF citations before returning the answer. Without an LLM, it returns labelled
source excerpts. Query embeddings run locally on CPU with multilingual-e5-small
through FastEmbed; the model and tokenizer are bundled in the Docker image.

See the [technical architecture](docs/architecture.zh-CN.md) for the complete design;
[data and implementation details](docs/implementation-notes.zh-CN.md) are maintained
separately. Cleaning, corpus construction, CPU retrieval, evidence assembly and the SDK search tool adapter are
implemented; the conversation runtime remains planned.

---

## Layout

```
raw data/
  mineru-official/           Verbatim MinerU output — never edited by hand
    content/                 Markdown + JSON + images/ (all three as siblings)
    MANIFEST.md              Provenance: tool, version, params, checksums, date
src/insuretutor/
  corpus.py                  Corpus models, offline builder, evidence assembly
  agent_tools.py             Read-only SDK search tool and per-turn citation registry
  ingest/                    cleaning (build-time only)
  retrieval/                 Offline CPU E5, BM25 + NumPy, RRF, evidence completion
  guardrails/                Refusal & scope policy
  tutor.py                   Full request lifecycle (to add)
  generation.py              Agents SDK runtime with optional supplemental searches (to add)
  api/                       FastAPI app
data/
  cleaning-rules.json        Source-pinned corrections, structure & evidence links
  cleaned/                   Generated clean fragments and provenance (implemented)
  corpus-rules.json          Reviewed language boundaries and context associations
  corpus.json                Runtime artifact (implemented)
  tokenizer/                 Pinned E5 tokenizer only, no embedding weights
  retrieval/                 FP32 vectors, manifest and retrieval evaluation reports
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
- [x] Source-verified bilingual lexical heading mappings
- [x] Cleaned fragments and reviewed metadata integrated into `corpus.json`
- [x] Local hybrid retrieval + complete evidence with citation anchors
- [x] Read-only SDK search tool + per-turn budgets and citation registry
- [ ] Agent query loop + answer generation + citation presentation
- [ ] Guardrails
- [ ] API + frontend
- [ ] Docker

## Credentials

No API keys in this repository. `.env` and `raw data/**/MANIFEST.local.*` are gitignored.
The runtime LLM key is supplied by whoever runs the container.
