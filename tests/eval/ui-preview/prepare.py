"""Build the test-only UI fixture from prewritten answers and corpus anchors."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

# UI examples select existing reference-answer sections, with reviewed citation
# bindings. This file and its generated data never enter Tutor or its index.
CASES = [
    (
        "withdrawal",
        "定期提款",
        "正文与脚注",
        "q5-",
        [
            ["note-6"],
            ["note-6"],
            ["note-6"],
            ["note-6"],
            ["note-7"],
            ["cash-value-risk", "term-and-lapse"],
        ],
    ),
    (
        "conflict",
        "双语金额冲突",
        "整表定位 · 双语对照",
        "q2-",
        [
            ["table-354-row-5"],
            ["table-354-row-5"],
            ["table-354-row-5"],
            ["table-354-row-5"],
        ],
    ),
    (
        "interest",
        "利率与回报",
        "跨页证据",
        "q3-",
        [
            [],
            ["extra-bonus-frequency"],
            ["bonus-rate-15-25", "bonus-rate-30"],
            [
                "base-interest",
                "additional-interest",
                "interest-year20-note",
                "interest-every5-note",
            ],
            ["extra-bonus-frequency", "interest-year20-note"],
            ["interest-guarantee"],
            ["rate-date-note", "bonus-rate-disclaimer"],
        ],
    ),
    (
        "calculation",
        "身故保障算例",
        "公式与适用脚注",
        "q4-",
        [
            ["table-97-row-3", "note-5"],
            [],
            ["table-97-row-3"],
            ["note-5"],
            ["table-97-row-3", "note-5"],
            ["table-97-row-3", "note-5"],
            ["note-4", "note-5"],
        ],
    ),
]

TITLES = {
    "withdrawal": "灵活套现",
    "note-6": "附注 6 · 定期提款条件",
    "note-7": "附注 7 · 主动提款费用",
    "cash-value-risk": "现金价值与费用风险",
    "term-and-lapse": "保单失效与宽限期",
    "table-354-row-5": "增加／减少保障额",
    "extra-bonus-frequency": "额外回报派发时间",
    "bonus-rate-15-25": "第 15／20／25 年回报率",
    "bonus-rate-30": "第 30 年起回报率",
    "base-interest": "基本派息",
    "additional-interest": "额外利息",
    "interest-year20-note": "额外利息 · 第 20 年",
    "interest-every5-note": "额外利息 · 其后每 5 年",
    "interest-guarantee": "账户价值下限保证",
    "rate-date-note": "假设息率与参考日期",
    "bonus-rate-disclaimer": "派发时适用比率",
    "table-97-row-3": "渐进寿险保障公式",
    "note-5": "附注 5 · 渐进保障扣减",
    "note-4": "附注 4 · 固定保障扣减",
}


def sections(answer: str) -> list[str]:
    result = []
    for paragraph in answer.split("\n\n"):
        # Keep indented calculation continuation lines with their numbered step.
        result.extend(p.strip() for p in re.split(r"(?m)(?=^\d+\))", paragraph) if p.strip())
    return result


def build():
    corpus = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))
    evaluation = json.loads((ROOT / "tests/eval/items.json").read_text(encoding="utf-8"))
    units = {u["id"]: u for u in corpus["units"]}
    spans = {s["id"]: s for s in corpus["source_spans"]}
    result = {"pdf_url": "source.pdf", "page_count": 20, "cases": []}
    for key, label, subtitle, prefix, bindings in CASES:
        item = next(i for i in evaluation["items"] if i["id"].startswith(prefix))
        parts = sections(item["expected_answer"])
        if key == "withdrawal":
            # Dataset commentary on parsing defects is not a customer UI answer.
            parts = parts[:-1]
        if len(parts) != len(bindings):
            raise ValueError(f"Reference answer changed: {item['id']}: {len(parts)} sections")
        case = {
            "id": key,
            "label": label,
            "subtitle": subtitle,
            "fixture_id": item["id"],
            "question": item["question"],
            "conflict": key == "conflict",
            "claims": [],
            "sources": [],
        }
        ordered_ids = list(dict.fromkeys(u for group in bindings for u in group))
        for index, uid in enumerate(ordered_ids, 1):
            unit = units[uid]
            for segment in unit["segments"]:
                source_ids = segment["source_span_ids"]
                body = [spans[s] for s in source_ids]
                context = [spans[s]["evidence_text"] for s in segment["context_span_ids"]]
                locations = []
                for span in body:
                    box = span["bbox_raw"]
                    assert len(box) == 4 and all(0 <= n <= 1000 for n in box)
                    location = {
                        "page": span["pdf_page"],
                        "bbox": box,
                        "precision": "table"
                        if span.get("bbox_precision") == "whole_table"
                        else "block",
                    }
                    if location not in locations:
                        locations.append(location)
                case["sources"].append(
                    {
                        "id": f"{uid}@{segment['language']}",
                        "unit_id": uid,
                        "number": index,
                        "title": TITLES.get(uid, uid),
                        "language": segment["language"],
                        "quote": "\n".join(s["evidence_text"] for s in body),
                        "context": " · ".join(dict.fromkeys(context)),
                        "locations": locations,
                        "span_ids": source_ids,
                    }
                )
        case["claims"] = [{"text": text, "unit_ids": ids} for text, ids in zip(parts, bindings)]
        result["cases"].append(case)
    target = HERE / "demo.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(result['cases'])} UI examples -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
