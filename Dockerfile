FROM python:3.12-slim-bookworm AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never PYTHONPATH=/app/src PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --extra agent --no-dev --no-install-project

FROM dependencies AS model
# Only the model preparation code invalidates this expensive download layer.
COPY src/insuretutor/__init__.py src/insuretutor/corpus.py ./src/insuretutor/
COPY src/insuretutor/ingest/ ./src/insuretutor/ingest/
COPY src/insuretutor/retrieval/ ./src/insuretutor/retrieval/
RUN .venv/bin/python -c "from insuretutor.retrieval.embedding import prepare_model; prepare_model()"

FROM dependencies AS runtime
ENV PATH=/app/.venv/bin:$PATH HF_HUB_OFFLINE=1 HOST=0.0.0.0 PORT=8000
RUN useradd --create-home --uid 10001 app
COPY --from=model /app/models/ ./models/
COPY src/insuretutor/ ./src/insuretutor/
COPY data/corpus.json ./data/corpus.json
COPY data/retrieval/manifest.json data/retrieval/vectors.npy ./data/retrieval/
COPY data/tokenizer/tokenizer.json ./data/tokenizer/tokenizer.json
COPY ["raw data/source/FLEXI-ULife Prime Saver.pdf", "raw data/source/FLEXI-ULife Prime Saver.pdf"]
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["python", "-m", "insuretutor.api"]
