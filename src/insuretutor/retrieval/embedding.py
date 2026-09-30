"""Pinned E5 assets and explicit, offline-only CPU inference."""

from __future__ import annotations

import hashlib
import unicodedata
from importlib.metadata import version
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from opencc import OpenCC

from insuretutor.corpus import (
    MAX_TOKENS,
    ROOT,
    TOKENIZER_REPOSITORY,
    TOKENIZER_REVISION,
    TOKENIZER_SHA256,
    load_tokenizer,
)

MODEL_DIR = ROOT / "models/multilingual-e5-small"
DIMENSION = 384
MODEL_ALIAS = "insuretutor/multilingual-e5-small-fp32"
# All files come from onnx/ at the same immutable upstream revision.
ASSETS = {
    "onnx/model.onnx": "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    "tokenizer.json": TOKENIZER_SHA256,
    "config.json": "bbb7c1333fc4b3e27fbc9cd5d2070aabcc1d4dfb99917c3633e772f97545a6b6",
    "tokenizer_config.json": "a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b",
    "special_tokens_map.json": "d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7",
}
CC = OpenCC("t2s")


class QueryInputError(ValueError):
    """Recoverable query validation error; artifact/inference failures are distinct."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_search(text: str) -> str:
    """Same Unicode, whitespace and script rules for documents and queries."""
    return " ".join(CC.convert(unicodedata.normalize("NFKC", text)).split())


def prefixed(text: str, kind: str) -> str:
    # Corpus views already carry passage:. Reject accidentally double-prefixed input.
    prefix = f"{kind}: "
    text = normalize_search(text)
    for known in ("query: ", "passage: "):
        if text.startswith(known):
            text = text[len(known) :]
            break
    if text.startswith(("query: ", "passage: ")):
        raise QueryInputError("Repeated E5 prefix")
    return prefix + text


def encoding_config() -> dict:
    return {
        "repository": TOKENIZER_REPOSITORY,
        "revision": TOKENIZER_REVISION,
        "assets_sha256": ASSETS,
        "dimension": DIMENSION,
        "dtype": "float32",
        "pooling": "attention_mask_mean",
        "normalization": "l2",
        "document_prefix": "passage: ",
        "query_prefix": "query: ",
        "special_tokens": True,
        "max_tokens": MAX_TOKENS,
        "search_normalization": "nfkc-whitespace-opencc-t2s/1",
        "fastembed": "0.8.1",
        "onnxruntime": "1.24.2",
        "tokenizers": "0.21.4",
        "opencc-python-reimplemented": "0.1.7",
        "numpy": "2.3.5",
        "provider": "CPUExecutionProvider",
    }


def prepare_model(directory: Path = MODEL_DIR) -> None:
    """The only network-enabled entry point; validate before atomically replacing files."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in ASSETS.items():
        target = directory / name
        if target.is_file() and sha256(target) == expected:
            print(f"Verified {name}", flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        remote_name = name if name.startswith("onnx/") else f"onnx/{name}"
        url = f"https://huggingface.co/{TOKENIZER_REPOSITORY}/resolve/{TOKENIZER_REVISION}/{remote_name}"
        temporary = target.with_suffix(target.suffix + ".part")
        print(f"Downloading {name}", flush=True)
        with urlopen(url, timeout=60) as source, temporary.open("wb") as output:
            while block := source.read(1024 * 1024):
                output.write(block)
        if sha256(temporary) != expected:
            temporary.unlink()
            raise ValueError(f"SHA-256 mismatch downloading {name}")
        temporary.replace(target)
        print(f"Verified {name}", flush=True)


class LocalE5Encoder:
    """One CPU session. Callers serialize encode operations in a worker thread."""

    def __init__(self, directory: Path = MODEL_DIR, threads: int = 2):
        if threads < 1:
            raise ValueError("Inference threads must be positive")
        self.threads = threads
        for package in (
            "fastembed",
            "onnxruntime",
            "tokenizers",
            "opencc-python-reimplemented",
            "numpy",
        ):
            if version(package) != encoding_config()[package]:
                raise ValueError(f"Unsupported {package} version: {version(package)}")
        for name, expected in ASSETS.items():
            path = directory / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing local model asset {path}; run prepare-model")
            if sha256(path) != expected:
                raise ValueError(f"Local model asset SHA-256 mismatch: {name}")
        # Import lazily: ordinary corpus/retrieval tests do not load weights.
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType

        if MODEL_ALIAS not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            TextEmbedding.add_custom_model(
                model=MODEL_ALIAS,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf=TOKENIZER_REPOSITORY),
                dim=DIMENSION,
                model_file="onnx/model.onnx",
            )
        self.tokenizer = load_tokenizer(directory / "tokenizer.json")
        self.model = TextEmbedding(
            model_name=MODEL_ALIAS,
            specific_model_path=str(directory.resolve()),
            local_files_only=True,
            providers=["CPUExecutionProvider"],
            threads=threads,
        )

    def _encode(self, texts: list[str], kind: str) -> np.ndarray:
        prepared = [prefixed(t, kind) for t in texts]
        for text in prepared:
            length = len(self.tokenizer.encode(text, add_special_tokens=True).ids)
            if length > MAX_TOKENS:
                raise QueryInputError(
                    f"E5 input has {length} tokens; limit {MAX_TOKENS}; no truncation"
                )
        if not texts:
            return np.empty((0, DIMENSION), dtype=np.float32)
        result = np.asarray(
            list(self.model.embed(prepared, batch_size=16, parallel=None)), dtype=np.float32
        )
        validate_vectors(result, len(texts))
        return result

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage")

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query")


def validate_vectors(vectors: np.ndarray, rows: int) -> None:
    if vectors.dtype != np.dtype("float32") or vectors.shape != (rows, DIMENSION):
        raise ValueError(
            f"Expected float32 vectors {(rows, DIMENSION)}, got {vectors.dtype} {vectors.shape}"
        )
    if not np.isfinite(vectors).all():
        raise ValueError("Vectors contain non-finite values")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5, rtol=0):
        raise ValueError("Vectors must have unit L2 norm")
