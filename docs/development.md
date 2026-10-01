# Development and evaluation

The reviewer quick start is in the [README](../README.md#quick-start).
Run the following commands from the repository root.

## Local development

Use uv and Python 3.12. Dependencies are declared in `pyproject.toml` and pinned
in `uv.lock`:

```powershell
uv sync --locked --extra agent --extra dev
uv run --locked --extra agent python -m insuretutor.retrieval prepare-model
uv run --locked --extra agent python -m insuretutor.api
```

Open <http://127.0.0.1:8000/>. Model preparation is a one-time download;
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
See [cleaning output](../data/cleaned/README.md),
[tokenizer](../data/tokenizer/README.md) and [vector artifacts](../data/retrieval/README.md).

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
[Evaluation questions and rubrics](../tests/eval/README.md) stay in tests and never
enter runtime prompts or indexes. Generated answers need semantic review;
citation coverage and a non-excerpt status do not prove correctness.

## Docker operations and configuration

```sh
docker compose ps
docker compose logs --tail 50
docker compose down
```

Set `PORT=8001` in `.env` if port 8000 is occupied. The container always listens
on 8000 internally; the Windows startup script opens the actual published port.
To reopen the default page without rebuilding:

```powershell
Start-Process 'http://127.0.0.1:8000/'
```

On macOS use `open http://127.0.0.1:8000/`; on desktop Linux use
`xdg-open http://127.0.0.1:8000/`.

LLM configuration uses `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL`.
The API must support Chat Completions function calls; provider JSON mode is not
required. Defaults are `LLM_REASONING_EFFORT=medium` and `LLM_MAX_TOKENS=32768`,
with a 60-second turn timeout. Leave reasoning effort blank for providers that
do not support it. A host-local API needs a container-accessible address;
`localhost` inside Docker points to the container itself.

`GET /api/health` reports retrieval readiness and `agent/excerpts` mode without
calling the LLM API. Container restart clears the in-memory sessions.
Missing, damaged or mismatched artifacts fail at startup; there is no automatic
rebuild or model download at runtime.

`.env`, local model weights, caches and `tmp/` are ignored. Build context excludes
secrets, tests and extraction intermediates. API keys are supplied only at runtime.
Optional re-parsing instructions are in the [provenance record](data-provenance.md).
