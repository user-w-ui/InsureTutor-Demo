# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**InsureTutor** — a grounded AI tutor over a 20-page bilingual (Traditional Chinese /
English) universal-life insurance brochure. Take-home task for the NUS AIDF AI Full
Stack Engineer internship. Requirements: [`docs/task-spec.md`](docs/task-spec.md).

The graded parts are conversation experience, **citation accuracy**, guardrail
robustness under misuse, Docker runnability, and documentation. Retrieval and citation
are where the difficulty actually lives, not the chat loop.

## Commands

```bash
# Install (editable, with optional extras)
pip install -e ".[dev]"
pip install -e ".[dev,embed]"     # adds sentence-transformers, only if eval shows it is needed

# Test
pytest                             # all
pytest tests/test_chunking.py      # one file
pytest tests/test_chunking.py::test_footnote_stays_with_referent   # one test

# Lint
ruff check src tests
ruff format src tests

# Run the API
uvicorn insuretutor.api.main:app --reload --port 8000

# Regenerate the corpus artifact (build-time only, offline, deterministic)
python -m insuretutor.ingest.build_corpus
```

`pyproject.toml` sets `pythonpath = ["src"]`, so tests import `insuretutor` without an
install step. Requires Python ≥ 3.11 (developed on 3.13).

## Architecture

The current design proposal is [`docs/architecture.md`](docs/architecture.md).
It supersedes the earlier retrieval details below: use table-row retrieval, mandatory
qualifying-note completion, separate language source anchors, and reviewed conflict
flags. The generated artifact is `data/corpus.json`. Runtime serves the original PDF
as a static citation target but never parses it. Citation existence and substring
matching do not establish semantic support. Preserve meaningful disclaimers even
when MinerU labels them `page_footnote`.

### The load-bearing decision: parse once, commit the artifact

```
   BUILD TIME (offline, deterministic, committed)         RUN TIME
   PDF ──► MinerU ──► raw data/ ──┐
                                  ├──► data/corpus.json
              data/curation.json ─┘          │
                                  docker run ─┘──► guardrail ──► retrieve ──► generate ──► verify
```

The container reads `data/corpus.json` and has no knowledge of MinerU, no PDF parsing
dependency, and no network need at startup. Re-parsing inside the container would
mean a multi-minute network-bound boot and citation anchors that drift between runs.

`build_corpus(raw, curation)` is a pure function of its two committed inputs, so the
pipeline re-runs to a byte-identical artifact. `data/curation.json` is the only
hand-authored input — it may declare relationships and flag conflicts, but **never
supplies or alters source text**. See [`docs/architecture.md`](docs/architecture.md)
for its schema and for the `Source span` / `Evidence group` / `Retrieval unit` model.

**Consequence for you:** `raw data/` is a frozen, verified input. Do not re-parse it or
hand-edit it. All transformation logic belongs in `src/insuretutor/ingest/` and outputs
to `data/`. If you think the parse is wrong, verify at the codepoint level first — see
"Traps" below, because two false alarms have already been raised this way.

### Page numbering — the one rule to get right

`page_idx + 1` is the **physical PDF page** and is the only citation anchor. The
brochure's *printed* page label is **not** a constant offset of it: numbering starts
after the cover and restarts (physical page 6 carries printed `1`). Read the printed
label from that page's own `page_number` block; never compute it. Full observed
mapping in [`docs/architecture.md`](docs/architecture.md) — getting this wrong
corrupts every citation card.

### Data contract — `raw data/mineru-official/`

Full schema in [`raw data/mineru-official/MANIFEST.md`](raw%20data/mineru-official/MANIFEST.md).
The parts that shape the ingest code:

- `content/*.json` — 380 blocks, each with `page_idx` (**0-based**) and `bbox`.
  This is the only artifact carrying page anchors, so **all citation provenance must
  come from the JSON, not the Markdown.**
- Block types: `text` (298, of which 72 carry `text_level` = headings), `table` (9),
  `image`/`chart` (33), plus **noise to filter before indexing**: `page_number` (16),
  `header` (14), `footer` (8), `page_footnote` (1), `aside_text` (1).
- `table.table_body` holds the structured `<table>` HTML — non-empty for all 9.
  `table_caption` / `table_footnote` are **empty arrays**; captions survive only as
  separate `text` blocks, so re-associate them by `page_idx` + proximity.
- Images live in `content/images/`, and both artifacts reference them as
  `images/<hash>.jpg` — already correct relative to `content/`, because MinerU writes
  the `.md`, the `.json`, and `images/` as siblings. **Leave that layout alone:** do not
  move `images/` out of `content/`, or all 33 in-prose links break in any Markdown
  viewer. There is no remap step; do not rewrite the artifacts.
- `.md` inlines 33 figures; `.json` carries 42 `img_path` entries. The extra 9 are
  rasterized table crops — the structured `<table>` HTML is authoritative for those.

### Retrieval design (decisions already made — see `docs/architecture.md` for reasoning)

- **Table-row, clause, and note granularity — not fixed windows.** Index individual
  clauses, disclosures, numbered notes, and table rows (rowspan/colspan resolved,
  headers carried into each row). The failure mode this prevents is concrete: `附註 3`
  holds the Guaranteed Insurability limits (25% cap, 51st birthday, max twice). Split it
  from the benefit it qualifies and the retriever surfaces the option name with no cap —
  confidently wrong. Junctions are declared in `curation.json`, not by proximity: the
  notes sit on physical page 12 while the benefits they qualify are on pages 5-11, so
  **spatial distance carries no signal here**. Missing note numbers (note 6) are
  recovered in curation.
- **Traditional → Simplified is one-way and index-side only** (OpenCC `t2s`). Display
  always shows the original Traditional, because a citation exists so a human can check
  it against the source. Never `s2t` on output. Simplified aliases are never citable.
- **Lexical first, vector only if measured necessary.** Start with rank-bm25 over
  deterministic tokens (Chinese character bigrams, English words, number/currency
  tokens). BM25 carries exact numbers (`2.5%`, `51歲`, `400,000`). Add multilingual
  embeddings only if the three-language evaluation set shows missing paraphrase recall —
  they are optional so the container can start with no model download.
- **No RAG framework, no vector DB.** 40k characters fit in memory; a framework would
  abstract away the one part that is actually graded.
- **Citation verification is load-bearing — and bounded.** Emit a citation only if the
  quoted span occurs in the chunk it names; downgrade unsupported answers rather than
  ship them. Be honest about the limit: substring match proves provenance, *not*
  semantic entailment. A supported number can still be attached to the wrong condition.
- **Two answer modes behind one interface:** LLM mode (user supplies an OpenAI-compatible
  key) and extractive mode (retrieval + citations, no synthesis, no key needed). The
  extractive mode is labelled as such in the UI and is never presented as generated
  tutoring.
- **Never stream unvalidated model tokens.** Return a pending state, validate, then
  deliver the final answer with server-built citations.


### Layout

```
raw data/source/            original PDF (served as a static citation target; never parsed)
raw data/mineru-official/   frozen parse: content/ (.md + .json + images/) + MANIFEST.md
data/curation.json          hand-authored links, note labels, reviewed conflicts
data/corpus.json            generated artifact (build-time only producer)
src/insuretutor/ingest/     raw artifacts + curation → data/corpus.json
src/insuretutor/retrieval/  lexical index + required-link completion + budgeting
src/insuretutor/guardrails/ refusal & scope policy
src/insuretutor/tutor.py    full request lifecycle (to add)
src/insuretutor/api/        FastAPI app
```

## Traps

**Do not verify Chinese text by reading terminal output.** A GBK/CP936 Windows console
renders correctly-stored Traditional Chinese as `���x�`. This has caused two false
"the parse is garbled" reports already. Verify by codepoint instead:

```bash
python -c "
import re
t=open('raw data/mineru-official/content/FLEXI-ULife Prime Saver.md',encoding='utf-8').read()
m=re.search(r'[\u4e00-\u9fff]{2,}',t)
print('CJK',len(re.findall(r'[\u4e00-\u9fff]',t)),'| U+FFFD',t.count(chr(0xFFFD)))
print([hex(ord(c)) for c in m.group()], m.group())
"
```

Or read with the Read tool / VS Code. `0x9078 0x64c7` is `選擇` — if you see those
codepoints, the file is fine and the terminal is lying.

Other specifics worth knowing:

- `page_idx` is **0-based**; `page_idx + 1` is the physical PDF page, and the printed
  page label is *not* a constant offset of it (see "Page numbering" above).
- Shell is PowerShell on this machine — `&&` chaining and heredocs differ. For long
  commit messages write to a temp file and use `git commit -F <file>`.
- No credentials in the repo. `.env` is gitignored; `.env.example` documents the vars.
  The `MINERU_TOKEN` for re-parsing is build-time only and never needed to run.
- The mineru.net **upload takes ~4 minutes**; pass `--timeout 1800`. The default 300 s
  fails on upload size, not on parsing — it is not a network or token problem.
- A block's `text` is the *only* place a note's number can appear, and MinerU sometimes
  drops it (physical page 12, note 6). Recover it in `curation.json`; do not regex-guess.
- Confirm the conflict row before citing it: physical page 17's minimum
  increase/decrease row disagrees between CN and EN (`40,000港元`/`400,000澳門元` vs
  `HK$400,000`/`MOP40,000`). Show both; never pick one.

## Status

Parse is done and verified. Blocked on two reviewed artefacts before `build_corpus` can
be written: the **nine-table / ten-note map** and the **bilingual glossary**
(see `docs/architecture.md`). Then: `data/corpus.json`, retrieval + citations,
guardrails, API + frontend, Docker. Tracked as a checklist in [`README.md`](README.md).

