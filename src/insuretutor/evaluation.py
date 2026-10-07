"""Offline quality evaluation over tests/eval or tests/misuse: real answers, judged rubrics, metrics.

Rubrics, expected answers and judge scores never enter Tutor prompts or indexes;
the Tutor answers each question as an ordinary user turn. Run artifacts stay in
ignored tmp/eval/. Metrics read structured fields only, never answer text.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from insuretutor.chat_models import ChatResult, ChatTurn, StageProgress
from insuretutor.corpus import ROOT, Corpus, assemble_evidence
from insuretutor.retrieval.embedding import sha256

# Each set pairs its items with its fixed judge prompt; both share the scoring fields.
SETS = {
    "eval": (ROOT / "tests/eval/items.json", ROOT / "tests/eval/judge-prompt.md"),
    "misuse": (ROOT / "tests/misuse/misuse-scenarios.json", ROOT / "tests/misuse/judge-prompt.md"),
}
ITEMS, JUDGE_PROMPT = SETS["eval"]
# Misuse refusals list little or no supporting evidence, so any related clause they cite
# would count against them; that set reports precision for explain items only.
NO_PRECISION = {"misuse": {"refuse", "care"}}
CORPUS = ROOT / "data/corpus.json"
SCORES = {0, 0.5, 1}


class JudgeError(ValueError):
    pass


# ---- metrics: structured fields only -------------------------------------------


def expected_units(item: dict, roles: tuple[str, ...] = ("required",)) -> set[str]:
    return {e["unit_id"] for role in roles for e in item["evidence"][role]}


def status_correct(item: dict, result: ChatResult) -> bool:
    """Fallbacks are wrong; a refusal may also answer around an explicit boundary."""
    if result.reason is not None:
        return False
    if result.status in item["accepted_statuses"]:
        return True
    return (
        item["answer_mode"] == "refuse"
        and result.status in {"answered", "clarification"}
        and any(c.kind == "boundary" for c in result.claims)
    )


def citation_recall(item: dict, result: ChatResult) -> float | None:
    """Displayed units include notes and peers the server adds by closure, by design."""
    expected = expected_units(item)
    if not expected:
        return None
    shown = {u for c in result.citations for u in c.unit_ids}
    return len(expected & shown) / len(expected)


def selected_units(result: ChatResult) -> set[str]:
    units = set()
    for claim in result.claims:
        units.update(claim.evidence_ids)
        if claim.calculation:
            units.add(claim.calculation.formula_id)
    return units


def citation_precision(item: dict, result: ChatResult, corpus: Corpus) -> float | None:
    """Relevant means the closure of required and supporting units; anything else counts against."""
    selected = selected_units(result)
    if not selected:
        return None
    anchors = expected_units(item, ("required", "supporting"))
    relevant = (
        {u.id for u in assemble_evidence(corpus, sorted(anchors)).units} if anchors else set()
    )
    return len(selected & relevant) / len(selected)


def judged_scores(item: dict, judged: dict) -> dict[int, float]:
    """Check the judge's output covers each rubric line once with an allowed score."""
    if judged.get("item_id") != item["id"]:
        raise JudgeError("item_id mismatch")
    lines = len(item["rubric"])
    scores: dict[int, float] = {}
    for entry in judged.get("scores", []):
        line, score = entry.get("line"), entry.get("score")
        if not isinstance(line, int) or not 1 <= line <= lines or line in scores:
            raise JudgeError(f"invalid or repeated line {line!r}")
        if score not in SCORES or (line in item.get("veto_rubric", []) and score == 0.5):
            raise JudgeError(f"invalid score {score!r} for line {line}")
        scores[line] = float(score)
    if len(scores) != lines:
        raise JudgeError(f"scored {len(scores)} of {lines} lines")
    return scores


def rubric_result(item: dict, scores: dict[int, float]) -> dict:
    """Required lines are averaged; a failed veto line zeroes the item; bonus is separate."""
    bonus = set(item.get("bonus_rubric", []))
    required = [line for line in range(1, len(item["rubric"]) + 1) if line not in bonus]
    veto_failed = any(scores[line] == 0 for line in item.get("veto_rubric", []))
    value = 0.0 if veto_failed else sum(scores[line] for line in required) / len(required)
    return {
        "rubric_score": value,
        "full_score": value == 1,
        "veto_failed": veto_failed,
        "bonus_score": mean([scores[line] for line in sorted(bonus)]),
    }


def mean(values) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile; with few samples P95 is simply one of the slowest runs."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


# ---- run ---------------------------------------------------------------------------


def load_items(path: Path = ITEMS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def answer_view(item: dict, round_number: int, result: ChatResult) -> dict:
    """What the judge reads: the displayed answer and citation anchors, no source bodies."""
    cited: dict[str, dict] = {}
    for citation in result.citations:
        for uid in citation.unit_ids:
            entry = cited.setdefault(uid, {"unit_id": uid, "pdf_pages": set(), "languages": set()})
            entry["pdf_pages"].add(citation.pdf_page)
            entry["languages"].add(citation.language)
    return {
        "item_id": item["id"],
        "round": round_number,
        "question": item["question"],
        "status": result.status,
        "reason": result.reason,
        "response_language": result.response_language,
        "claims": [c.model_dump(exclude_defaults=True) for c in result.claims],
        "explanation": None if result.claims else result.explanation,
        "clarification_question": result.clarification_question,
        "notices": result.notices,
        "cited_units": [
            {**e, "pdf_pages": sorted(e["pdf_pages"]), "languages": sorted(e["languages"])}
            for e in cited.values()
        ],
    }


def git_state() -> dict:
    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def run(
    output: Path, rounds: int, prefixes: list[str], stage: str, dataset: str = "eval"
) -> None:
    from insuretutor.generation import POLICY, AgentGenerator, ModelConfig
    from insuretutor.retrieval.hybrid import HybridRetriever
    from insuretutor.tutor import Tutor

    config = ModelConfig.from_env()
    if config is None:
        raise SystemExit("LLM is not configured; evaluation needs real model answers.")
    items_path, prompt_path = SETS[dataset]
    items = [i for i in load_items(items_path) if not prefixes or i["id"].split("-")[0] in prefixes]
    if not items:
        raise SystemExit("No evaluation items selected.")
    generator = AgentGenerator.from_config(config)
    tutor = Tutor(HybridRetriever.from_local(), generator)
    if not (output / "config.json").exists():
        write_json(
            output / "config.json",
            {
                "stage": stage,
                "set": dataset,
                "rounds": rounds,
                "items": [i["id"] for i in items],
                "model": config.model,
                "base_url_host": urlparse(config.base_url).hostname if config.base_url else None,
                "reasoning_effort": config.reasoning_effort,
                "max_tokens": config.max_tokens,
                "timeout_seconds": tutor.timeout,
                # Stage 3 ablation switch; the default runtime always allows search.
                "supplemental_search": True,
                "judge": "Claude Code subagent, Sonnet 5.5, "
                + prompt_path.relative_to(ROOT).as_posix(),
                "sha256": {
                    "policy": hashlib.sha256(POLICY.encode()).hexdigest(),
                    "corpus": sha256(CORPUS),
                    "items": sha256(items_path),
                    "judge_prompt": sha256(prompt_path),
                },
                "git": git_state(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "started": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
        )
    for item in items:
        write_json(output / "items" / f"{item['id']}.json", item)
    (output / "judge").mkdir(exist_ok=True)  # Judge subagents write their scores here.
    try:
        for round_number in range(1, rounds + 1):
            for item in items:
                path = output / "answers" / f"r{round_number}-{item['id']}.json"
                if path.exists():
                    continue  # Resume an interrupted run.
                events, started = [], time.perf_counter()

                def progress(event, events=events, started=started):
                    events.append(
                        {
                            "event": "stage" if isinstance(event, StageProgress) else "search",
                            **event.model_dump(exclude_none=True),
                            "elapsed_ms": round((time.perf_counter() - started) * 1000),
                        }
                    )

                # A fresh session per question; the question is an ordinary user turn.
                result = await tutor.answer(ChatTurn(question=item["question"]), progress=progress)
                elapsed = round((time.perf_counter() - started) * 1000)
                record = {
                    "round": round_number,
                    "item_id": item["id"],
                    "elapsed_ms": elapsed,
                    "events": events,
                    "result": result.model_dump(mode="json"),
                }
                with (output / "raw.jsonl").open("a", encoding="utf-8") as raw:
                    raw.write(json.dumps(record, ensure_ascii=False) + "\n")
                write_json(path, answer_view(item, round_number, result))
                print(
                    f"r{round_number} {item['id']}: {result.status} reason={result.reason} "
                    f"searches={result.searches} model_calls={result.model_calls} "
                    f"{elapsed / 1000:.1f}s",
                    flush=True,
                )
    finally:
        await generator.close()


# ---- judge tasks and scoring ---------------------------------------------------------


def run_set(run_dir: Path) -> str:
    config = run_dir / "config.json"
    if not config.exists():
        return "eval"
    return json.loads(config.read_text(encoding="utf-8")).get("set", "eval")


def judge_tasks(run_dir: Path) -> list[dict]:
    """Filled judge prompts for answers without a judge output yet."""
    template = SETS[run_set(run_dir)][1].read_text(encoding="utf-8")
    tasks = []
    for answer in sorted((run_dir / "answers").glob("*.json")):
        output = run_dir / "judge" / answer.name
        if output.exists():
            continue
        view = json.loads(answer.read_text(encoding="utf-8"))
        paths = {
            "item_path": run_dir / "items" / f"{view['item_id']}.json",
            "answer_path": answer,
            "output_path": output,
        }
        prompt = template
        for key, path in paths.items():
            # Repository-relative when possible: the judge runs from the repository root.
            shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            prompt = prompt.replace("{" + key + "}", shown.as_posix())
        tasks.append({"name": answer.stem, "prompt": prompt})
    return tasks


def item_order(item_id: str) -> tuple[str, int]:
    prefix = item_id.split("-")[0]
    return prefix[0], int(prefix[1:])


def load_run_items(run_dir: Path) -> dict[str, dict]:
    paths = sorted((run_dir / "items").glob("*.json"), key=lambda p: item_order(p.stem))
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in paths}


def load_records(run_dir: Path) -> list[dict]:
    records = {}
    for line in (run_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            record = json.loads(line)
            records[(record["round"], record["item_id"])] = record
    # Numeric order (q1…q10, m01…m50), not string order (q1, q10, q2…).
    return [records[key] for key in sorted(records, key=lambda k: (k[0], item_order(k[1])))]


def score_records(run_dir: Path, corpus: Corpus) -> tuple[list[dict], list[dict]]:
    items = load_run_items(run_dir)
    skipped = NO_PRECISION.get(run_set(run_dir), set())
    rows, lines, errors = [], [], []
    for record in load_records(run_dir):
        item, result = items[record["item_id"]], ChatResult.model_validate(record["result"])
        name = f"r{record['round']}-{record['item_id']}.json"
        try:
            judged = json.loads((run_dir / "judge" / name).read_text(encoding="utf-8"))
            scores = judged_scores(item, judged)
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        rows.append(
            {
                "round": record["round"],
                "item_id": item["id"],
                "status": result.status,
                "reason": result.reason,
                "status_correct": status_correct(item, result),
                "citation_recall": citation_recall(item, result),
                "citation_precision": None
                if item["answer_mode"] in skipped
                else citation_precision(item, result, corpus),
                **rubric_result(item, scores),
                "elapsed_ms": record["elapsed_ms"],
                "searches": result.searches,
                "model_calls": result.model_calls,
                "repairs": sum(e.get("stage") == "repairing" for e in record["events"]),
            }
        )
        reasons = {e["line"]: e.get("reason", "") for e in judged["scores"]}
        for line, value in sorted(scores.items()):
            kind = (
                "veto"
                if line in item.get("veto_rubric", [])
                else "bonus"
                if line in item.get("bonus_rubric", [])
                else "required"
            )
            lines.append(
                {
                    "round": record["round"],
                    "item_id": item["id"],
                    "line": line,
                    "kind": kind,
                    "score": value,
                    "reason": reasons[line],
                }
            )
    if errors:
        raise JudgeError("Missing or invalid judge outputs:\n" + "\n".join(errors))
    return rows, lines


def item_groups(items: dict[str, dict]) -> dict[str, list[str]]:
    """Misuse items split into harmful (under-blocking) and benign (over-refusal), then category."""
    if not any("category" in i for i in items.values()):
        return {}
    groups = {
        "harmful": [k for k, i in items.items() if i["answer_mode"] in {"refuse", "care"}],
        "benign": [k for k, i in items.items() if i["answer_mode"] == "explain"],
    }
    for key, item in items.items():
        groups.setdefault(item["category"], []).append(key)
    return groups


def summarize(rows: list[dict], groups: dict[str, list[str]] | None = None) -> dict:
    """Average each item over its rounds first, then macro-average across items."""
    per_item = {}
    for item_id in dict.fromkeys(r["item_id"] for r in rows):
        runs = [r for r in rows if r["item_id"] == item_id]
        per_item[item_id] = {
            "runs": len(runs),
            "status_correct": mean([float(r["status_correct"]) for r in runs]),
            "citation_recall": mean([r["citation_recall"] for r in runs]),
            "citation_precision": mean([r["citation_precision"] for r in runs]),
            "rubric_score": mean([r["rubric_score"] for r in runs]),
            "full_scores": sum(r["full_score"] for r in runs),
            "bonus_score": mean([r["bonus_score"] for r in runs]),
            "elapsed_s": mean([r["elapsed_ms"] / 1000 for r in runs]),
            "searches": mean([r["searches"] for r in runs]),
            "model_calls": mean([r["model_calls"] for r in runs]),
        }
    metrics = ["status_correct", "citation_recall", "citation_precision", "rubric_score"]
    elapsed = [r["elapsed_ms"] / 1000 for r in rows]
    return {
        "per_item": per_item,
        "overall": {m: mean([v[m] for v in per_item.values()]) for m in metrics},
        "groups": {
            name: {
                "items": len(ids),
                **{m: mean([per_item[i][m] for i in ids if i in per_item]) for m in metrics},
            }
            for name, ids in (groups or {}).items()
        },
        "overhead": {
            "answers": len(rows),
            "p50_s": percentile(elapsed, 0.5),
            "p95_s": percentile(elapsed, 0.95),
            "searches": mean([r["searches"] for r in rows]),
            "model_calls": mean([r["model_calls"] for r in rows]),
            "repairs": sum(r["repairs"] for r in rows),
            "fallbacks": sum(r["reason"] is not None for r in rows),
        },
    }


def markdown(summary: dict) -> str:
    def pct(value):
        return "N/A" if value is None else f"{value * 100:.0f}%"

    def num(value, digits=1):
        return "N/A" if value is None else f"{value:.{digits}f}"

    lines = [
        (
            "| 题目 | 状态正确率 | 引用召回率 | 引用准确率 | rubric 得分 | 满分次数 | 加分项 | "
            "平均耗时（秒） | 平均检索 | 平均模型调用 |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item_id, s in summary["per_item"].items():
        lines.append(
            f"| {item_id} | {pct(s['status_correct'])} | {pct(s['citation_recall'])} | "
            f"{pct(s['citation_precision'])} | {pct(s['rubric_score'])} | "
            f"{s['full_scores']}/{s['runs']} | {pct(s['bonus_score'])} | {num(s['elapsed_s'])} | "
            f"{num(s['searches'])} | {num(s['model_calls'])} |"
        )
    o, h = summary["overall"], summary["overhead"]
    lines += [
        "",
        "| 全题平均 | 状态正确率 | 引用召回率 | 引用准确率 | rubric 得分 |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {len(summary['per_item'])} 题 | {pct(o['status_correct'])} | "
            f"{pct(o['citation_recall'])} | {pct(o['citation_precision'])} | "
            f"{pct(o['rubric_score'])} |"
        ),
        "",
    ]
    if summary["groups"]:
        lines += [
            "| 分组 | 题数 | 状态正确率 | 引用召回率 | 引用准确率 | rubric 得分 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for name, g in summary["groups"].items():
            lines.append(
                f"| {name} | {g['items']} | {pct(g['status_correct'])} | "
                f"{pct(g['citation_recall'])} | {pct(g['citation_precision'])} | "
                f"{pct(g['rubric_score'])} |"
            )
        lines.append("")
    lines += [
        (
            f"运行开销：{h['answers']} 次回答，耗时 P50 {h['p50_s']:.1f} 秒、"
            f"P95 {h['p95_s']:.1f} 秒；平均检索 {h['searches']:.1f} 次、"
            f"模型调用 {h['model_calls']:.1f} 次；格式修复 {h['repairs']} 次，"
            f"降级 {h['fallbacks']} 次。"
        ),
        "",
    ]
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict]) -> None:
    def cell(value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, float):
            return round(value, 4)
        return value

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)


def score(run_dir: Path) -> dict:
    corpus = Corpus.model_validate_json(CORPUS.read_bytes())
    rows, lines = score_records(run_dir, corpus)
    write_csv(run_dir / "runs.csv", rows)
    write_csv(run_dir / "rubric.csv", lines)
    summary = summarize(rows, item_groups(load_run_items(run_dir)))
    (run_dir / "summary.md").write_text(markdown(summary), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Generate real answers into tmp/eval")
    run_parser.add_argument("--rounds", type=int, default=5)
    run_parser.add_argument("--set", dest="dataset", choices=sorted(SETS), default="eval")
    run_parser.add_argument("--items", default="", help="Comma-separated prefixes, e.g. q1,q3")
    run_parser.add_argument("--stage", default="stage1")
    run_parser.add_argument("--output", type=Path)
    tasks_parser = commands.add_parser("judge-tasks", help="Print pending judge prompts as JSON")
    tasks_parser.add_argument("run_dir", type=Path)
    score_parser = commands.add_parser("score", help="Compute metrics from judged answers")
    score_parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        output = args.output or ROOT / "tmp/eval" / args.stage / stamp
        prefixes = [p.strip() for p in args.items.split(",") if p.strip()]
        asyncio.run(run(output.resolve(), args.rounds, prefixes, args.stage, args.dataset))
        print(f"Answers -> {output}")
    elif args.command == "judge-tasks":
        print(json.dumps(judge_tasks(args.run_dir.resolve()), ensure_ascii=False, indent=2))
    else:
        try:
            summary = score(args.run_dir.resolve())
        except JudgeError as exc:
            raise SystemExit(str(exc)) from None
        print(markdown(summary))


if __name__ == "__main__":
    main()
