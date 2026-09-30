# Local retrieval artifacts

- `vectors.npy`: 275 × 384, NumPy float32, L2-normalized; 422,528 bytes.
- `manifest.json`: corpus SHA-256, ordered view IDs, fixed asset SHA-256 and encoding configuration.
- `evaluation.json`: seven positive scenarios, each with English, Simplified Chinese,
  Traditional Chinese and the original question (28 searches), without rewriting.

Run from the repository root after `pip install -e ".[dev]"`:

```text
python -m insuretutor.retrieval prepare-model
python -m insuretutor.retrieval build-index
python -m insuretutor.retrieval evaluate
```

Only preparation downloads files. Model assets are kept in ignored `models/`, pinned
to `intfloat/multilingual-e5-small` revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
The FP32 ONNX model has SHA-256
`ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`.
Tokenizer SHA-256 matches the committed [tokenizer](../tokenizer/README.md).
Upstream model license: MIT. No quantized / FP16 substitute is used.

Vectors are derived, not citation text. Every row maps to its original view in the
manifest; each view maps to a full parent unit in `corpus.json`. Corpus mismatch,
row-order mismatch, encoding mismatch, bad checksum, wrong dtype/shape, non-finite
values and non-unit vectors are rejected at initialization. Nothing auto-rebuilds.

Recall@5 uses unique primary unit IDs before evidence completion; core coverage uses
an explicit required-ID list after completion, so equivalent evidence in other table
rows can be undercounted. Required-evidence coverage separately checks `requires`
closure of selected evidence. Relevance coverage and footnote completeness are different
metrics. Full queries, selected IDs, missing IDs, environment and timings are in each report.
See [implementation notes](../../docs/implementation-notes.zh-CN.md) for interpretation.
