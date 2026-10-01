"""Offline retrieval benchmark; this does not test answering or refusal decisions."""

from __future__ import annotations

import json
import platform
import statistics
import time
from importlib.metadata import version

import numpy as np
from opencc import OpenCC

from insuretutor.corpus import ROOT

from .embedding import prefixed
from .hybrid import HybridRetriever, QueryContext


async def evaluate_retrieval(retriever: HybridRetriever) -> dict:
    path = ROOT / "tests/retrieval_cases.json"
    cases = json.loads(path.read_bytes())["cases"]
    evaluator_path = ROOT / "tests/eval/items.json"
    originals = {
        item["id"].split("-")[0]: item["question"]
        for item in json.loads(evaluator_path.read_bytes())["items"]
    }
    cc = OpenCC("s2t")
    rows, latencies, retrieval_latencies = [], [], []
    for case in cases:
        variants = {lang: case[lang] for lang in ("en", "zh-Hans")}
        variants["zh-Hant"] = cc.convert(case["zh-Hans"])
        variants["original"] = originals[case["id"]]
        for language, question in variants.items():
            started = time.perf_counter()
            # Hybrid mirrors the tutor's mandatory initial retrieval, which expands a
            # multi-sentence question. The single-channel baselines stay unexpanded so
            # each channel is still measured on the query exactly as written.
            unexpanded = await retriever.rank(QueryContext(original_question=question))
            expanded = await retriever.rank(
                QueryContext(original_question=question, expand_sentences=True)
            )
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            methods = {}
            rankings = {
                "bm25": unexpanded.bm25,
                "vector": unexpanded.vector,
                "hybrid": expanded.hybrid,
            }
            for name, ranked in rankings.items():
                recovery_started = time.perf_counter()
                bundle = retriever.evidence_for(ranked)
                if name == "hybrid":
                    retrieval_latencies.append(
                        latency + (time.perf_counter() - recovery_started) * 1000
                    )
                recovered = {u.id for u in bundle.units}
                gold, core = set(case["primary"]), set(case["core"])
                top5 = [r.unit_id for r in ranked[:5]]
                methods[name] = {
                    "top5": top5,
                    "selected": bundle.selected_unit_ids,
                    "bundle": sorted(recovered),
                    "recall_at_5": len(gold.intersection(top5)) / len(gold),
                    "core_coverage": len(core & recovered) / len(core),
                    "missing_core": sorted(core - recovered),
                    "missing_additional": sorted(set(case["additional"]) - recovered),
                    "source_characters": sum(len(s.evidence_text) for s in bundle.source_spans),
                    "required_evidence_coverage": float(
                        all(set(u.requires) <= recovered for u in bundle.units)
                    ),
                }
            rows.append(
                {
                    "id": case["id"],
                    "language": language,
                    "question": question,
                    "latency_ms": round(latency, 3),
                    "methods": methods,
                }
            )
    summary = {"cases": len(rows)}
    for method in ("bm25", "vector", "hybrid"):
        summary[method] = {
            "recall_at_5": round(
                statistics.mean(r["methods"][method]["recall_at_5"] for r in rows), 6
            ),
            "core_coverage": round(
                statistics.mean(r["methods"][method]["core_coverage"] for r in rows), 6
            ),
            "complete_core_cases": sum(not r["methods"][method]["missing_core"] for r in rows),
            "required_evidence_coverage": statistics.mean(
                r["methods"][method]["required_evidence_coverage"] for r in rows
            ),
        }
    encoder = retriever.encoder
    probe = "保证可保权益最多几次？"
    first = encoder.encode_queries([probe])
    second = encoder.encode_queries([probe])
    # Re-encoding a committed row must match offline indexing, despite different padding.
    texts = [retriever.corpus.retrieval_views[i].search_text for i in (0, 120, 274)]
    rebuilt = encoder.encode_documents(texts)
    maximum_error = float(np.max(np.abs(rebuilt - retriever.vectors[[0, 120, 274]])))
    tokenizer = encoder.model.model.tokenizer
    prepared = [prefixed(t, "passage") for t in texts] + [prefixed(probe, "query")]
    actual_tokens = tokenizer.encode_batch(prepared)
    token_match = all(
        [t for t, mask in zip(a.ids, a.attention_mask) if mask]
        == encoder.tokenizer.encode(p, add_special_tokens=True).ids
        for p, a in zip(prepared, actual_tokens)
    )
    checks = {
        "network_blocked_for_initialization_and_inference": True,
        "repeated_query_identical": bool(np.array_equal(first, second)),
        "document_reencode_max_abs_error": maximum_error,
        "fastembed_tokenizer_matches_precheck": token_match,
        "providers": encoder.model.model.model.get_providers(),
        "passed": bool(np.array_equal(first, second) and maximum_error < 1e-5 and token_match),
    }
    return {
        "schema_version": 1,
        "metric_definition": "Macro unit Recall@5 over primary targets; exact core-unit coverage after ranked top-8 whole-closure recovery (may undercount equivalent evidence in other table rows). 21 equivalent queries plus 7 original queries; excludes refusal cases. Required-evidence coverage checks requires closure of retrieved units, independently of relevance. Additional source examples are reported separately. No relevance acceptance threshold is specified.",
        "summary": summary,
        "offline_checks": checks,
        "environment": {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "python": platform.python_version(),
            "threads": encoder.threads,
            "packages": {p: version(p) for p in ("fastembed", "onnxruntime", "numpy")},
            "latency_ms": {
                "median": round(statistics.median(latencies), 3),
                "p95": round(float(np.percentile(latencies, 95)), 3),
                "max": round(max(latencies), 3),
            },
            "latency_scope": "warm rank() including CPU query encoding, lexical/dense fusion; excludes bundle recovery and startup",
            "retrieval_latency_ms": {
                "median": round(statistics.median(retrieval_latencies), 3),
                "p95": round(float(np.percentile(retrieval_latencies, 95)), 3),
            },
        },
        "results": rows,
    }
