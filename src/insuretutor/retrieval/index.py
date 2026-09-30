"""Deterministic vector artifacts. Loading never rebuilds or downloads anything."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from insuretutor.corpus import ROOT, Corpus

from .embedding import LocalE5Encoder, encoding_config, sha256, validate_vectors

INDEX_DIR = ROOT / "data/retrieval"
CORPUS_PATH = ROOT / "data/corpus.json"


def load_corpus(path: Path = CORPUS_PATH) -> Corpus:
    return Corpus.model_validate_json(path.read_bytes())


def build_index(
    encoder: LocalE5Encoder, corpus_path: Path = CORPUS_PATH, directory: Path = INDEX_DIR
) -> dict:
    corpus = load_corpus(corpus_path)
    vectors = encoder.encode_documents([v.search_text for v in corpus.retrieval_views])
    validate_vectors(vectors, len(corpus.retrieval_views))
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "vectors.tmp"
    with temporary.open("wb") as output:
        np.save(output, vectors, allow_pickle=False)
    temporary.replace(directory / "vectors.npy")
    manifest = {
        "schema_version": 1,
        "corpus_sha256": sha256(corpus_path),
        "view_ids": [v.id for v in corpus.retrieval_views],
        "encoding": encoding_config(),
        "vectors_sha256": sha256(directory / "vectors.npy"),
    }
    (directory / "manifest.json").write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
    )
    return manifest


def load_index(
    corpus: Corpus, corpus_path: Path = CORPUS_PATH, directory: Path = INDEX_DIR
) -> np.ndarray:
    manifest = json.loads((directory / "manifest.json").read_bytes())
    expected = {
        "schema_version": 1,
        "corpus_sha256": sha256(corpus_path),
        "view_ids": [v.id for v in corpus.retrieval_views],
        "encoding": encoding_config(),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Retrieval artifact mismatch: {key}; rebuild explicitly")
    path = directory / "vectors.npy"
    if sha256(path) != manifest.get("vectors_sha256"):
        raise ValueError("Retrieval vector SHA-256 mismatch")
    vectors = np.load(path, allow_pickle=False)
    validate_vectors(vectors, len(corpus.retrieval_views))
    vectors.flags.writeable = False
    return vectors
