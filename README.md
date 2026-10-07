# InsureTutor

An insurance-brochure chat demo for the AIDF AI Full Stack Engineer take-home task.
Ask in English, Simplified Chinese or Traditional Chinese; click answer references
to inspect the original PDF alongside the conversation.

## How it works

Local CPU **multilingual-e5-small + BM25**, fused with **RRF**, retrieve bilingual
clauses and their required footnotes. **OpenCC** normalizes Chinese search text.
The application guarantees an initial search; an **OpenAI Agents SDK** agent can
use one read-only search tool to obtain further evidence before answering.

**FastAPI** serves the static chat page and local **PDF.js** viewer in one container.
The server builds quotes, physical page links and block/table highlights. Fixed
model instructions, restricted tools, format/reference validation and safe text
rendering define the safety boundary; source conflicts retain both language versions.

## Quick start

Start Docker Desktop (Linux containers) or Docker Engine with Compose v2.
No host Python or model installation is required. Run from the repository root:

1. Create `.env` if needed:

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

2. Set `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` in `.env`.
   Use a Chat Completions API supporting **function calls**.
   Without LLM configuration, the demo displays original source excerpts.

3. **Windows — build, start and automatically open the chat page:**

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1
   ```

   **Other platforms — build and wait until ready:**

   ```sh
   docker compose up --build --wait --wait-timeout 180
   ```

   Open [the chat page](http://127.0.0.1:8000/). Stop with `docker compose down`.

The first build downloads dependencies and the pinned E5 model (about 487 MB);
subsequent builds reuse the model cache. Embeddings run locally; only answer
generation calls the configured LLM API. Select a language and send a question;
while it is answered, the page shows each search and agent step as it happens, then
the validated answer with that process collapsed above it.
**New chat** or a page refresh starts a new conversation.

## Evaluation

Offline baseline, 10 questions × 5 rounds with a Sonnet rubric judge: answer status
100% correct, citation recall 92%, citation precision 79%, rubric score 89%. Factual,
cross-language and refusal questions hold up; the vague purchase question is the main
weakness. On 50 misuse scenarios (1 round) every injection, fraud and out-of-scope request was refused or bounded, no
benign look-alike was refused (rubric 91%); self-harm handling and the duty of disclosure in fraud
refusals are the gaps. Details in the [evaluation report (中文)](docs/evaluation.zh-CN.md).

## Key links

| Location | Contents |
| --- | --- |
| [Architecture (中文)](docs/architecture.zh-CN.md) | Components, retrieval flow, citations and safety design |
| [Original PDF](raw%20data/source/FLEXI-ULife%20Prime%20Saver.pdf) · [MinerU output](raw%20data/mineru-official/MANIFEST.md) | Source brochure and frozen extraction |
| [Runtime corpus](data/corpus.json) | Bilingual clauses, footnotes and provenance |
| [Vector artifacts](data/retrieval/README.md) | Precomputed vectors and model metadata |
| [Evaluation set](tests/eval/README.md) | Questions, source references and rubrics |
| [Misuse scenarios](tests/misuse/README.md) | Injection, fraud, self-harm, personal-data and out-of-scope cases with benign look-alikes |
| [Evaluation report (中文)](docs/evaluation.zh-CN.md) · per-run results: [stage 1](results/stage1-runs.csv), [stage 2](results/stage2-runs.csv) | Metrics, baseline and misuse results, limitations |
| [Development guide](docs/development.md) | Local installation, CLI, artifact rebuilding and evaluation commands |
| [Task specification](docs/task-spec.md) | Original requirements |

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
  evaluation.py             Offline quality evaluation: real answers, judged rubrics, metrics
  api/                      FastAPI entry point
  web/                      Static chat UI and vendored PDF.js
data/                       Cleaned data, corpus, tokenizer and vector artifacts
raw data/                   Original PDF and frozen MinerU extraction
docs/                       Architecture, development guide, evaluation report and source research
tests/                      Offline contracts and evaluation fixtures
results/                    Published per-run evaluation results
scripts/start-demo.ps1      Build, wait and open the web page
Dockerfile                 Locked runtime dependencies and cached model download
docker-compose.yml         Local-only port and runtime LLM configuration
```
