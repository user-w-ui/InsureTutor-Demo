"""Interactive CLI and explicit test-file evaluation (not runtime prompt fixtures)."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import time
from pathlib import Path

from pydantic import ValidationError

from insuretutor.chat_models import ChatResult, ChatTurn
from insuretutor.generation import AgentGenerator, ModelConfig
from insuretutor.retrieval.embedding import MODEL_DIR
from insuretutor.retrieval.hybrid import HybridRetriever
from insuretutor.retrieval.index import CORPUS_PATH, INDEX_DIR
from insuretutor.sessions import SessionCapacityError
from insuretutor.tutor import Tutor


def display(result: ChatResult):
    print(f"\n[{result.status}] {result.response_language} | session={result.session_id}")
    print(result.explanation)
    if result.reason:
        print(f"Reason: {result.reason}")
    for notice in result.notices:
        print(notice)
    if result.clarification_question:
        print(result.clarification_question)
    for c in result.citations:
        print(f"\n[{', '.join(c.unit_ids)} | {c.language} | PDF physical page {c.pdf_page}]")
        print(c.quote)
    print(f"\nsearches={result.searches}; model_calls={result.model_calls}")


async def evaluate(tutor: Tutor, fixture: Path, progress=None) -> dict:
    """Questions enter only as user turns; answers/rubrics never enter the model."""
    source = json.loads(fixture.read_text(encoding="utf-8"))
    rows = []
    for item in source["items"]:
        turns = item.get("turns") or [
            {
                "question": item["question"],
                "response_language": item.get("response_language", "auto"),
            }
        ]
        sid = None
        for index, turn in enumerate(turns):
            started = time.perf_counter()
            result = await tutor.answer(
                ChatTurn(
                    question=turn["question"],
                    session_id=sid,
                    response_language=turn.get("response_language", "auto"),
                )
            )
            sid = result.session_id
            expected = set(turn.get("expected_unit_ids", []))
            if not expected and index == len(turns) - 1:
                expected = set(item.get("expected_unit_ids", [])) or {
                    e["unit_id"] for e in item.get("evidence", {}).get("required", [])
                }
            actual = {u for c in result.citations for u in c.unit_ids}
            rows.append(
                {
                    "id": item["id"],
                    "turn": index + 1,
                    "result": result.model_dump(),
                    "expected_unit_ids": sorted(expected),
                    "missing_unit_ids": sorted(expected - actual),
                    "citation_coverage": len(expected & actual) / len(expected)
                    if expected
                    else None,
                    "needs_human_semantic_review": True,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            )
            if progress:
                progress(rows[-1])
    return {
        "generated_answers": sum(
            r["result"]["status"] not in {"excerpts", "insufficient"} for r in rows
        ),
        "total_turns": len(rows),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "reasoning_effort": tutor.generator.reasoning_effort if tutor.generator else None,
            "max_tokens": tutor.generator.max_tokens if tutor.generator else None,
        },
        "cases": rows,
        "note": "Citation coverage is not a semantic/arithmetic accuracy score. Review answers and safety manually.",
    }


async def run(args):
    retriever = HybridRetriever.from_local(args.corpus, args.index_dir, args.model_dir, 2)
    generator = None
    if not args.excerpts:
        try:
            config = ModelConfig.from_env()
            generator = AgentGenerator.from_config(config) if config else None
        except (ValueError, ImportError):
            print("Model configuration or SDK dependency invalid; using source excerpt mode.")
    tutor = Tutor(retriever, generator)
    try:
        if args.evaluate:

            def progress(row):
                result = row["result"]
                print(
                    f"{row['id']} turn {row['turn']}: {result['status']} "
                    f"(searches={result['searches']}, model_calls={result['model_calls']}, "
                    f"reason={result['reason'] or 'none'})",
                    flush=True,
                )

            report = await evaluate(tutor, args.evaluate, progress)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(
                f"Generated {report['generated_answers']}/{report['total_turns']} turns -> {args.output}"
            )
            if not generator:
                print("Excerpt-only run; real model acceptance remains pending.")
            return
        if args.question:
            display(
                await tutor.answer(
                    ChatTurn(question=args.question, response_language=args.language)
                )
            )
            return
        sid = None
        print("InsureTutor: /new starts a conversation; /exit quits.")
        if generator is None:
            print("Source excerpt mode (model disabled or .env not configured).")
        while True:
            try:
                question = await asyncio.to_thread(input, "\nYou> ")
            except EOFError:
                return
            if question.strip() == "/exit":
                return
            if question.strip() == "/new":
                sid = None
                print("New conversation.")
                continue
            if not question.strip():
                continue
            try:
                result = await tutor.answer(
                    ChatTurn(question=question, session_id=sid, response_language=args.language)
                )
            except (ValidationError, SessionCapacityError):
                print("Invalid input or all sessions busy. Question limit: 4,000 characters.")
                continue
            sid = result.session_id
            display(result)
    finally:
        if generator:
            await generator.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--question", "-q")
    mode.add_argument("--evaluate", type=Path, help="Explicit evaluation JSON file")
    parser.add_argument("--language", choices=["auto", "en", "zh-Hans", "zh-Hant"], default="auto")
    parser.add_argument("--excerpts", action="store_true", help="Disable generation")
    parser.add_argument("--output", type=Path, default=Path("tmp/chat-evaluation.json"))
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument("--index-dir", type=Path, default=INDEX_DIR)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except ValidationError:
        raise SystemExit("Invalid question; limit: 4,000 characters.") from None


if __name__ == "__main__":
    main()
