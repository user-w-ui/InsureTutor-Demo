"""Run model preparation, indexing, retrieval diagnostics and multilingual evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from .embedding import MODEL_DIR, LocalE5Encoder, prepare_model
from .hybrid import HybridRetriever, QueryContext
from .index import CORPUS_PATH, INDEX_DIR, build_index


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--index-dir", type=Path, default=INDEX_DIR)
    parser.add_argument("--threads", type=int, default=2)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare-model")
    commands.add_parser("build-index")
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--rewrite")
    query.add_argument("--language", choices=["auto", "en", "zh-Hans", "zh-Hant"], default="auto")
    query.add_argument("--output", type=Path)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--output", type=Path, default=INDEX_DIR / "evaluation.json")
    args = parser.parse_args()
    if args.command == "prepare-model":
        prepare_model(args.model_dir)
        return
    if args.command == "build-index":
        manifest = build_index(
            LocalE5Encoder(args.model_dir, args.threads), args.corpus, args.index_dir
        )
        print(f"Built {len(manifest['view_ids'])} FP32 document vectors")
        return
    # The benchmark must prove local initialization AND inference work with no sockets.
    offline = (
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        if args.command == "evaluate"
        else nullcontext()
    )
    with offline:
        retriever = HybridRetriever.from_local(
            args.corpus, args.index_dir, args.model_dir, args.threads
        )
    if args.command == "evaluate":
        from .evaluation import evaluate_retrieval

        async def run_evaluation():
            # Enter after asyncio creates its Windows loopback socket pair.
            with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
                return await evaluate_retrieval(retriever)

        report = asyncio.run(run_evaluation())
        write_json(args.output, report)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        print(f"Full evaluation -> {args.output}")
        if not report["offline_checks"]["passed"]:
            raise SystemExit("Offline/configuration checks failed")
        if report["summary"]["hybrid"]["required_evidence_coverage"] != 1:
            raise SystemExit("Mandatory evidence recovery failed")
        return

    async def run_query():
        rankings = await retriever.rank(
            QueryContext(
                original_question=args.question,
                rewritten_query=args.rewrite,
                response_language=args.language,
            )
        )
        bundle = retriever.evidence_for(rankings.hybrid)
        return {
            "rankings": {
                k: [asdict(u) for u in getattr(rankings, k)] for k in ("bm25", "vector", "hybrid")
            },
            "evidence": bundle.model_dump(),
        }

    result = asyncio.run(run_query())
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
