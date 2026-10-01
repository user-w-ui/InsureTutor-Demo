# InsureTutor

A bilingual insurance-brochure chat demo for the AIDF AI Full Stack Engineer
take-home task. Ask in English, Simplified Chinese or Traditional Chinese, then
follow each answer's references to the original PDF in the same page.

**For reviewers:** [Technical architecture (中文)](docs/architecture.zh-CN.md) ·
[Implementation notes and known limits (中文)](docs/implementation-notes.zh-CN.md) ·
[Original task](docs/task-spec.md)

## Quick start: Docker and the web page

Start Docker Desktop (Linux containers), or a Docker Engine with Compose v2.
The Docker path needs no host Python, uv, model files or source mounts.
Run these commands from the repository root.

1. Create `.env` if it does not exist:

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

2. Fill in `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL`. The API must support
   Chat Completions **function calls**; provider JSON mode is unnecessary.
   The tested settings are `LLM_REASONING_EFFORT=medium` and
   `LLM_MAX_TOKENS=32768`. Leave reasoning effort blank for providers that do not
   support it. Without a key/model, the demo runs in labelled original-excerpt mode.

3. **Windows: build, wait until ready, and automatically open the browser:**

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1
   ```

   The script opens the actual published port, including a custom `PORT` in `.env`.
   To reopen the default page when the container is already running:

   ```powershell
   Start-Process 'http://127.0.0.1:8000/'
   ```

On any platform, the equivalent build/start command is:

```sh
docker compose up --build --wait --wait-timeout 180
```

The default page is <http://127.0.0.1:8000/>. To open it from a terminal on
macOS use `open http://127.0.0.1:8000/`; on desktop Linux use
`xdg-open http://127.0.0.1:8000/`.

The first build needs internet access for the Python image, locked dependencies
and about 487 MB of pinned E5 assets. Later builds reuse the model layer.
Runtime embeddings load locally on CPU; only answer generation contacts the LLM API.
An API hosted on your computer needs a container-accessible address rather than
`localhost`, which refers to the container itself.

```sh
docker compose ps                         # container readiness
docker compose logs --tail 50             # startup / request status
docker compose down                      # stop
```

If port 8000 is occupied, set `PORT=8001` in `.env` and rerun the startup script.
The container still listens on 8000 internally. Refreshing the page or selecting
**New chat** starts a new conversation; container restart clears server sessions.
`GET /api/health` reports retrieval readiness and `agent/excerpts` mode, without
checking the remote model API.

## Design

A single container serves FastAPI, static HTML/CSS/JavaScript and local PDF.js.
The server retrieves the original question first. One OpenAI Agents SDK agent
can supplement that evidence through the read-only `search_evidence` tool.

- **Small local retrieval:** multilingual-e5-small on CPU, BM25 + NumPy cosine
  search, equal RRF. Precomputed vectors and a few hundred views make a vector
  database or FAISS unnecessary; the caller depends on one `Retriever` interface.
- **Complete evidence:** restore bilingual parents and required footnotes, retain
  table headers and both sides of source conflicts. OpenCC normalizes Chinese
  search text; citations keep the original Traditional Chinese / English text.
- **References:** the server creates original quotes, physical PDF pages and
  block/table coordinates. The page supports source-language switching and zoom;
  highlights show text blocks or whole tables, not exact sentences or cells.
- **Bounded conversation:** at most 6 searches per turn, a 60-second total timeout,
  one format/reference repair, and bounded in-memory history.
- **Safety:** fixed model instructions, a read-only tool, current-turn citation
  allowlists and safe text rendering. Validation checks format and submitted
  reference provenance; it does not judge answer meaning, completeness, uncited
  text, safety wording or arithmetic. Those require model evaluation and review.

The source is the 20-page YF Life **FLEXI-ULife Prime Saver** brochure. A known
Chinese/English currency discrepancy is retained, with details in the
[implementation notes](docs/implementation-notes.zh-CN.md).

## Local development

Use uv and Python 3.12. Dependencies are declared in `pyproject.toml` and pinned
in `uv.lock`:

```powershell
uv sync --locked --extra agent --extra dev
uv run --locked --extra agent python -m insuretutor.retrieval prepare-model
uv run --locked --extra agent python -m insuretutor.api
```

Open the same web address as above. Model preparation is a one-time download;
model files live in ignored `models/`. Missing or mismatched local artifacts fail
explicitly, without automatic downloads or rebuilding.

### Data and index rebuilding

The committed `data/corpus.json` is the runtime input: 137 logical pairs,
274 independent language records, 660 monolingual source spans and 275 retrieval
views. The committed float32 vector matrix has 275 × 384 entries.
Only rebuild these artifacts when changing their inputs or encoding:

```powershell
uv run --locked --extra agent python -m insuretutor.ingest.clean
uv run --locked --extra agent python -m insuretutor.corpus
uv run --locked --extra agent python -m insuretutor.retrieval build-index
```

`raw data/` is frozen. Reviewed corrections, language boundaries and footnote
relationships belong to `data/cleaning-rules.json`. Corpus assembly restores
complete conditions; source text, ranges and pages remain traceable.
See [cleaning output](data/cleaned/README.md),
[tokenizer](data/tokenizer/README.md) and [vector artifacts](data/retrieval/README.md).

### CLI and evaluation

```powershell
uv run --locked --extra agent python -m insuretutor.chat
uv run --locked --extra agent python -m insuretutor.chat --question "定期提款有什么条件？" --language zh-Hans
uv run --locked --extra agent python -m insuretutor.chat --question "Withdrawal conditions?" --excerpts
uv run --locked --extra agent python -m insuretutor.retrieval query "保證可保權益最多可行使幾次？" --output tmp/query.json

# Offline contracts; no model API or embedding weights required.
uv run --locked --extra agent --extra dev python -m pytest -q

# Real local E5 benchmark; no LLM API. Save a fresh report separately.
uv run --locked --extra agent python -m insuretutor.retrieval evaluate --output tmp/retrieval-evaluation.json

# Real LLM runs require .env and consume provider tokens.
uv run --locked --extra agent python -m insuretutor.chat --evaluate tests/eval/items.json --output tmp/chat-evaluation.json
uv run --locked --extra agent python -m insuretutor.chat --evaluate tests/eval/chat-scenarios.json --output tmp/chat-scenarios.json
```

CLI commands: `/new`, `/exit`; languages: `auto/en/zh-Hans/zh-Hant`.
[Evaluation questions and rubrics](tests/eval/README.md) stay in tests and never
enter runtime prompts or indexes. Generated answers need semantic review;
citation coverage and a non-excerpt status do not prove correctness.

## Layout

```text
src/insuretutor/
  corpus.py                 Data contracts, corpus builder and evidence assembly
  ingest/                   Offline cleaning
  retrieval/                Local E5, BM25 + NumPy, RRF and retrieval benchmark
  agent_tools.py            Mandatory initial search and read-only search tool
  tutor.py / generation.py  Turn lifecycle and bounded Agents SDK loop
  chat_models.py            Request, answer and model-draft contracts
  sessions.py / guardrails/ History, format/reference checks and citations
  references.py             Web reference groups
  chat.py                   Interactive / evaluation CLI
  api/                      FastAPI entry point
  web/                      Static chat UI and vendored PDF.js
 data/                      Cleaned data, corpus, tokenizer and vector artifacts
 raw data/                  Original PDF and frozen MinerU extraction
 docs/                      Architecture, implementation notes and source research
 tests/                     Offline contracts and evaluation fixtures
 scripts/start-demo.ps1     Build, wait and open the web page
 Dockerfile                 Locked runtime dependencies and cached model download
 docker-compose.yml         Local-only port and runtime LLM configuration
```

Re-parsing is optional; the extraction is already committed. See the
[provenance record](docs/data-provenance.md) for that historical workflow.
`.env`, local model weights, caches and `tmp/` are ignored. Build context excludes
secrets, tests and extraction intermediates. API keys are supplied only at runtime.
