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
pip install -e ".[dev,embed]"     # adds sentence-transformers for the vector half

# Test
pytest                             # all
pytest tests/test_chunking.py      # one file
pytest tests/test_chunking.py::test_footnote_stays_with_referent   # one test

# Lint
ruff check src tests
ruff format src tests

# Run the API
uvicorn insuretutor.api.main:app --reload --port 8000

# Regenerate the retrieval artifact (build-time only)
python -m insuretutor.ingest.build_chunks
```

`pyproject.toml` sets `pythonpath = ["src"]`, so tests import `insuretutor` without an
install step. Requires Python ≥ 3.11 (developed on 3.13).

## Architecture

### The load-bearing decision: parse once, commit the artifact

```
   BUILD TIME (done, committed)                    RUN TIME
   PDF ──► MinerU ──► raw data/ ──► chunks ──► data/chunks.json
                                                     │
                                        docker run ──┘──► retrieve ──► answer
```

The container reads `data/chunks.json` and has no knowledge of MinerU, no PDF
dependency, and no network need at startup. Re-parsing inside the container would
mean a multi-minute network-bound boot and citation anchors that drift between runs.

**Consequence for you:** `raw data/` is a frozen, verified input. Do not re-parse it or
hand-edit it. All transformation logic belongs in `src/insuretutor/ingest/` and outputs
to `data/`. If you think the parse is wrong, verify at the codepoint level first — see
"Traps" below, because two false alarms have already been raised this way.

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
- Images live in `assets/images/`, but artifacts reference them as `images/<hash>.jpg`.
  Resolve `images/x.jpg` → `../assets/images/x.jpg` (relative to `content/`) once in
  the ingest layer. **Do not rewrite the artifacts to fix this.**

### Retrieval design (decisions already made — see `docs/architecture.md` for reasoning)

- **Semantic-anchor chunking, not fixed windows.** A chunk is one clause, one numbered
  footnote, or one table. The failure mode this prevents is concrete: `附註 3` holds the
  Guaranteed Insurability limits (25% cap, 51st birthday, max twice). Split it from the
  table row referencing it and the retriever surfaces the option name with no cap —
  confidently wrong. Chunks carry `refs` so retrieval can pull the referent in.
- **Traditional → Simplified is one-way and index-side only** (OpenCC `t2s`). Display
  always shows the original Traditional, because a citation exists so a human can check
  it against the source. Never `s2t` on output.
- **Hybrid BM25 + vector.** BM25 carries exact numbers (`2.5%`, `51歲`, `400,000`);
  vector carries paraphrase ("what if I lose my job" → 失業保障). Vector is optional so
  the container can run with no model download.
- **No RAG framework, no vector DB.** 40k characters fit in memory; a framework would
  abstract away the one part that is actually graded.
- **Citation verification is load-bearing.** Emit a citation only if the quoted span
  occurs in the chunk it names. Downgrade unsupported answers rather than ship them.
- **Two answer modes behind one interface:** LLM mode (user supplies an OpenAI-compatible
  key) and offline/extractive mode (retrieval + citations, no synthesis, no key needed).

### Layout

```
raw data/source/            original PDF (never read at run time)
raw data/mineru-official/   frozen parse: content/ + assets/images/ + MANIFEST.md
src/insuretutor/ingest/     PDF artifacts → data/chunks.json (build-time only)
src/insuretutor/retrieval/  hybrid index + ref-aware rerank
src/insuretutor/guardrails/ refusal & scope policy
src/insuretutor/api/        FastAPI app
data/                       committed build artifacts
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

- `page_idx` is **0-based**; every human-facing citation needs `+1`.
- Shell is PowerShell on this machine — `&&` chaining and heredocs differ. For long
  commit messages write to a temp file and use `git commit -F <file>`.
- No credentials in the repo. `.env` is gitignored; `.env.example` documents the vars.
  The `MINERU_TOKEN` for re-parsing is build-time only and never needed to run.
- The mineru.net **upload takes ~4 minutes**; pass `--timeout 1800`. The default 300 s
  fails on upload size, not on parsing — it is not a network or token problem.

## Status

Parse is done and verified. Remaining: `data/chunks.json`, retrieval + citations,
guardrails, API + frontend, Docker. Tracked as a checklist in
[`README.md`](README.md).
