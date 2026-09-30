"""Offline, source-pinned cleaning of this brochure; no model or network calls.

Run: python -m insuretutor.ingest.clean
The output is an intermediate evidence dataset, not a vector index or runtime API.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "raw data/mineru-official/content/FLEXI-ULife Prime Saver.json"
PDF = ROOT / "raw data/source/FLEXI-ULife Prime Saver.pdf"
RULES = ROOT / "data/cleaning-rules.json"
CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CJK = re.compile(r"[\u3400-\u9fff]")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def language(text: str) -> str:
    zh, en = bool(CJK.search(text)), bool(re.search(r"[A-Za-z]{2,}", text))
    return "mixed" if zh and en else "zh-Hant" if zh else "en" if en else "und"


def normalize(text: str, markers=(), markup_refs=()) -> tuple[str, list[int], list[str]]:
    """Remove presentation syntax, not mathematical meaning or arbitrary digits.

    A bare/markup numeral is a footnote ONLY at a reviewed source location.
    Literal anchors contain their trailing reference number and are exact matches.
    """
    refs, flags = set(), []
    text = html.unescape(text)
    text = re.sub(r"\\([$*#])", r"\1", text)

    def superscript(match):
        value = match.group(1).strip()
        if value.isdigit() and int(value) in markup_refs:
            refs.add(int(value))
            return " "
        if value in {"st", "nd", "rd", "th", "*", "#", "^"}:
            return value
        flags.append("unresolved_superscript")
        return "^{" + value + "}"

    text = re.sub(r"<sup>(.*?)</sup>", superscript, text, flags=re.S)
    text = re.sub(r"<sub>(.*?)</sub>", r"_{\1}", text, flags=re.S)
    text = re.sub(r"\$(\d+)\^\{(st|nd|rd|th)\}\$", r"\1\2", text)
    text = re.sub(r"\$\^\{(\d+)\}\$", superscript, text)
    for rule in markers:
        anchor, number = rule["anchor"], rule["number"]
        if not anchor.endswith(str(number)) or text.count(anchor) != 1:
            raise ValueError(f"Stale or ambiguous reference anchor: {anchor!r}")
        start = text.index(anchor)
        end = start + len(anchor)
        replacement = anchor[:-len(str(number))]
        if (replacement[-1:].isascii() and replacement[-1:].isalpha()
                and text[end:end + 1].isascii() and text[end:end + 1].isalpha()):
            replacement += " "
        text = text[:start] + replacement + text[end:]
        refs.add(number)
    if set(markup_refs) - refs:
        raise ValueError("Expected markup reference is missing")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"(\d+(?:st|nd|rd|th))(?=[A-Za-z])", r"\1 ", text)
    if CONTROLS.search(text):
        flags.append("damaged_text")
        text = CONTROLS.sub("[解析缺字]", text)
    text = re.sub(r"[ \t\r\n]+", " ", text).strip()
    return text, sorted(refs), sorted(set(flags))


class TableParser(HTMLParser):
    """Keep cell HTML and origin positions while expanding merged cells."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.rows = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in {"td", "th"}:
            attrs = dict(attrs)
            self.cell = {"raw_html": "", "rowspan": int(attrs.get("rowspan", 1)),
                         "colspan": int(attrs.get("colspan", 1))}
            if not (1 <= self.cell["rowspan"] <= 100 and 1 <= self.cell["colspan"] <= 100):
                raise ValueError("Invalid table span")
        elif self.cell is not None:
            self.cell["raw_html"] += self.get_starttag_text()

    def handle_endtag(self, tag):
        if tag in {"td", "th"}:
            if self.cell is None or not self.rows:
                raise ValueError("Malformed table cell")
            self.rows[-1].append(self.cell)
            self.cell = None
        elif self.cell is not None:
            self.cell["raw_html"] += f"</{tag}>"

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["raw_html"] += data

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")

    def expanded(self, block_key):
        occupied, cells = {}, []
        for row, values in enumerate(self.rows):
            col = 0
            for cell in values:
                while (row, col) in occupied:
                    col += 1
                cell = dict(cell, key=f"{block_key}:r{row}:c{col}", row=row, col=col)
                cells.append(cell)
                for r in range(row, row + cell["rowspan"]):
                    for c in range(col, col + cell["colspan"]):
                        if (r, c) in occupied or r >= len(self.rows):
                            raise ValueError("Overlapping or out-of-range table cells")
                        occupied[r, c] = cell["key"]
                col += cell["colspan"]
        width = max((c for _, c in occupied), default=-1) + 1
        grid = [[occupied.get((r, c)) for c in range(width)] for r in range(len(self.rows))]
        return cells, grid


def unique(items):
    return list(dict.fromkeys(items))


def expand_required(units: list[dict], selected: list[str]) -> list[dict]:
    """Complete dependencies without ranking/truncating qualifying notes away."""
    lookup = {unit["id"]: unit for unit in units}
    result, seen = [], set()

    def visit(key):
        if key in seen:
            return
        seen.add(key)
        unit = lookup[key]  # dangling relationships must fail, not silently disappear
        result.append(unit)
        for required in unit["requires"]:
            visit(required)

    for key in selected:
        visit(key)
    return result


def build(raw_bytes: bytes, rules: dict, pdf_bytes: bytes) -> dict:
    if digest(raw_bytes) != rules["raw_sha256"] or digest(pdf_bytes) != rules["pdf_sha256"]:
        raise ValueError("Source hash changed; review cleaning-rules.json before rebuilding")
    raw = json.loads(raw_bytes)
    if len(raw) != 380 or {b["page_idx"] for b in raw} != set(range(20)):
        raise ValueError("Unexpected source structure")
    prefix = "flexi-" + digest(raw_bytes)[:12]
    spans, blocks, tables, assets, ledger, issues = {}, [], [], [], [], []
    unit_map, consumed = {}, set()

    def add_span(key, block_index, value, **extra):
        block = raw[block_index]
        clean, refs, flags = normalize(value, rules["literal_markers"].get(key, []),
                                       rules["markup_reference_locations"].get(key, []))
        flags = sorted(set(flags + rules["block_flags"].get(str(block_index), [])))
        span = {"id": f"{prefix}/{key}", "source_key": key, "block_index": block_index,
                "pdf_page": block["page_idx"] + 1, "bbox_raw": block["bbox"],
                "raw_text": value, "clean_text": clean, "language": language(clean),
                "note_refs": refs, "quality_flags": flags,
                "quote_policy": "raw_text_only; normalized text is not a verbatim quotation",
                **extra}
        spans[key] = span
        for flag in flags:
            issues.append({"source_key": key, "pdf_page": span["pdf_page"], "issue": flag,
                           "status": "unresolved", "action": "preserve source; inspect PDF"})
        return span

    def add_unit(key, body_keys, context_keys=(), notes=(), requires=(), kind="clause",
                 pairing="same_topic_not_equivalence", **extra):
        if key in unit_map:
            raise ValueError(f"Duplicate unit: {key}")
        body_keys, context_keys = unique(body_keys), unique(context_keys)
        selected = [spans[k] for k in unique(list(context_keys) + body_keys)]
        refs = sorted(set(notes).union(*(s["note_refs"] for s in selected)))
        needed = unique(list(requires) + [f"note-{n}" for n in refs])
        text = "\n".join(unique(s["clean_text"] for s in selected if s["clean_text"]))
        unit_map[key] = {
            "id": key, "evidence_group": key, "kind": kind,
            "source_span_ids": [spans[k]["id"] for k in body_keys],
            "context_span_ids": [spans[k]["id"] for k in context_keys],
            "source_keys": body_keys, "pages": sorted({s["pdf_page"] for s in selected}),
            "languages": sorted({s["language"] for s in selected}),
            "text": text, "note_refs": refs, "requires": [n for n in needed if n != key],
            "pairing_status": pairing,
            "quality_flags": sorted({f for s in selected for f in s["quality_flags"]}),
            "indexable": kind != "fragment", **extra,
        }

    metadata_indices = set(rules["metadata_blocks"].values())
    for index, block in enumerate(raw):
        key, kind = f"b{index}", block["type"]
        action = ""
        if index in metadata_indices:
            action = "metadata_only"
        elif kind in rules["excluded_types"]:
            action = "excluded_layout_noise"
        elif kind in {"image", "chart"}:
            action = "asset_not_text_indexed"
            assets.append({"block_index": index, "pdf_page": block["page_idx"] + 1,
                           "raw": block, "status": "not_transcribed",
                           "reason": "Visual assets retained; decorative/informative not assumed"})
        elif kind in {"text", "page_footnote"}:
            span = add_span(key, index, block.get("text", ""))
            blocks.append({"block_index": index, "original_type": kind,
                           "clean_type": "disclaimer" if kind == "page_footnote" else kind,
                           "text_level": block.get("text_level"), **span})
            action = "retained_text" if span["clean_text"] else "empty_text"
        elif kind == "table":
            parser = TableParser()
            parser.feed(block["table_body"])
            cells, grid = parser.expanded(key)
            for cell in cells:
                cell["span_id"] = add_span(cell["key"], index, cell["raw_html"],
                                           table_row=cell["row"], table_col=cell["col"],
                                           bbox_precision="whole_table")["id"]
            captions = []
            for n, caption in enumerate(block.get("table_caption", [])):
                caption_key = f"{key}:caption:{n}"
                add_span(caption_key, index, caption, kind="native_table_caption")
                captions.append(caption_key)
            tables.append({"block_index": index, "pdf_page": block["page_idx"] + 1,
                           "bbox_raw": block["bbox"], "raw_html": block["table_body"],
                           "image_path": block["img_path"], "caption": block["table_caption"] or None,
                           "caption_keys": captions, "caption_status": "native" if captions else "absent",
                           "cells": cells, "grid": grid,
                           "review_status": "structure_checked_by_agent_not_full_transcription_review"})
            action = "retained_table"
        else:
            raise ValueError(f"Unaccounted block type: {kind}")
        ledger.append({"block_index": index, "original_type": kind,
                       "pdf_page": block["page_idx"] + 1, "action": action})

    # Pinned source groups combine parallel passages without translating or losing anchors.
    for group in rules["groups"]:
        body = [f"b{i}" for i in group["blocks"]]
        headings = [f"b{i}" for i in group["headings"]]
        consumed.update(group["blocks"] + group["headings"])
        add_unit(group["id"], body, headings, group["notes"],
                 rules["mandatory_links"].get(group["id"], []), group["kind"],
                 group["pairing_status"])

    for table in tables:
        index = table["block_index"]
        spec = rules["tables"][str(index)]
        cells = {c["key"]: c for c in table["cells"]}
        grid = table["grid"]
        context = [f"b{i}" for i in spec["context_blocks"]] + table["caption_keys"]
        consumed.update(spec["context_blocks"])
        for row, row_keys in enumerate(grid):
            if row in spec["header_rows"] or row in spec["skip_rows"]:
                continue
            body = unique(k for k in row_keys if k and spans[k]["clean_text"])
            if body and all(spans[k]["clean_text"] in {"·", "…", "."} for k in body):
                continue  # ellipsis row: not a fact and not an interpolation instruction
            inherited = spec["header_rows"] + spec.get("row_headers", {}).get(str(row), [])
            headers = unique(k for r in inherited for k in grid[r] if k)
            headings = unique(context + headers)
            notes = spec.get("row_notes", {}).get(str(row), [])
            requires = spec.get("requires", []) + spec.get("row_requires", {}).get(str(row), [])
            variants = spec.get("split_rows", {}).get(str(row), [])
            if variants:
                # Split only by audited exact substrings. No replacement text is supplied.
                for variant in variants:
                    selected = []
                    for key in body:
                        if key not in variant["selectors"]:
                            selected.append(key)
                            continue
                        value = variant["selectors"][key]
                        original = cells[key]["raw_html"]
                        if original.count(value) != 1:
                            raise ValueError(f"Ambiguous cell selector: {key}")
                        part_key = key + ":" + variant["name"]
                        start = original.index(value)
                        add_span(part_key, index, original[start:start + len(value)],
                                 table_row=row, table_col=cells[key]["col"],
                                 parent_source_key=key, raw_char_range=[start, start + len(value)],
                                 bbox_precision="whole_table")
                        selected.append(part_key)
                    nested_headers = unique(k for k in grid[row - 1] if k)
                    add_unit(f"table-{index}-row-{row}-{variant['name']}", selected,
                             headings + nested_headers, notes, requires, "table_row")
                continue
            key = f"table-{index}-row-{row}"
            conflict = row in spec.get("conflict_rows", [])
            add_unit(key, body, headings, notes, requires, spec.get("kind", "table_row"),
                     "reviewed_source_conflict" if conflict else "same_topic_not_equivalence",
                     conflict=conflict, table_block=index, table_row=row)
            # Targeted column labels survive rowspan/colspan and preserve age/amount relationships.
            bindings = []
            for col, cell_key in enumerate(row_keys):
                if cell_key and col == cells[cell_key]["col"]:
                    covered = range(col, col + cells[cell_key]["colspan"])
                    labels = unique(grid[r][c] for r in inherited for c in covered
                                    if grid[r][c] and grid[r][c] != cell_key
                                    and spans[grid[r][c]]["clean_text"])
                    bindings.append({"cell": spans[cell_key]["id"],
                                     "column_headers": [spans[k]["id"] for k in labels]})
            unit_map[key]["cell_bindings"] = bindings
            if bindings and inherited:
                labelled = []
                for binding in bindings:
                    by_id = {s["id"]: s for s in spans.values()}
                    label = " / ".join(by_id[i]["clean_text"] for i in binding["column_headers"])
                    value = by_id[binding["cell"]]["clean_text"]
                    if value:
                        labelled.append(f"{label}: {value}" if label else value)
                unit_map[key]["text"] = "\n".join(
                    unique([spans[k]["clean_text"] for k in context] + labelled))

    # Two single-language allocation tables become two bilingual row units, not four hits.
    for row in (1, 2):
        left = unit_map.pop(f"table-231-row-{row}")
        right = unit_map.pop(f"table-252-row-{row}")
        add_unit(f"asset-allocation-row-{row}", left["source_keys"] + right["source_keys"],
                 ["b227", "b248", "b231:r0:c0", "b231:r0:c1", "b252:r0:c0", "b252:r0:c1"],
                 requires=["investment-strategy-changes"], kind="table_row")

    # Retain remaining text; do not silently infer a counterpart or index isolated labels.
    for block in blocks:
        index, text = block["block_index"], block["clean_text"]
        if index in consumed:
            continue
        if not text or block["text_level"] or len(text) < 16:
            ledger[index]["action"] = "retained_context_only"
            continue
        key = f"unpaired-block-{index}"
        add_unit(key, [f"b{index}"], kind="unpaired", pairing="unpaired")
        issues.append({"source_key": f"b{index}", "issue": "unpaired_text",
                       "status": "needs_review", "action": "kept, not forcibly translated or paired"})

    units = list(unit_map.values())
    for conflict in rules["conflicts"]:
        unit_map[conflict["unit"]]["conflict_detail"] = conflict["reason"]
    # Flag span quality at unit level, even when the other language remains usable.
    for unit in units:
        unit["review_status"] = "needs_review" if unit["quality_flags"] else "structure_checked"
        if unit["kind"] == "fragment":
            unit["review_status"] = "needs_visual_transcription"
        unit["evidence_group"] = rules.get("evidence_groups", {}).get(unit["id"], unit["id"])
    source_ids = {s["id"] for s in spans.values()}
    for unit in units:
        if not unit["text"].strip():
            raise ValueError("Empty retrieval unit")
        for sid in unit["source_span_ids"] + unit["context_span_ids"]:
            if sid not in source_ids:
                raise ValueError(f"Dangling source: {sid}")
        for dependency in unit["requires"]:
            if dependency not in unit_map:
                raise ValueError(f"Dangling required evidence: {dependency}")
        expand_required(units, [unit["id"]])
    matched_literals = set(rules["literal_markers"]) - set(spans)
    if matched_literals:
        raise ValueError(f"Unused literal marker locations: {matched_literals}")

    report = {
        "status": "cleaned_with_explicit_review_items",
        "input_blocks": len(raw), "input_types": dict(Counter(b["type"] for b in raw)),
        "actions": dict(Counter(row["action"] for row in ledger)),
        "retained_text_blocks": len(blocks), "tables": len(tables),
        "native_caption_tables": sum(bool(t["caption"]) for t in tables),
        "source_spans": len(spans), "retrieval_units": len(units),
        "indexable_units": sum(u["indexable"] for u in units),
        "numbered_note_groups": len(rules["note_blocks"]),
        "required_edges": sum(len(u["requires"]) for u in units),
        "conflicts": rules["conflicts"], "issues": issues,
        "control_character_occurrences": sum(len(CONTROLS.findall(b.get("text", ""))) for b in raw),
        "verified_printed_pages": rules["verified_printed_pages"],
        "scope": "No source text corrections, translation, vector index, or whole-PDF transcription review.",
        "review": rules["review"],
    }
    manifest = {
        "schema_version": 1, "source_id": prefix, "source_json_sha256": digest(raw_bytes),
        "source_pdf_sha256": digest(pdf_bytes),
        "source_json": "raw data/mineru-official/content/FLEXI-ULife Prime Saver.json",
        "source_pdf": "raw data/source/FLEXI-ULife Prime Saver.pdf",
        "metadata": {key: {"raw_text": raw[i]["text"], "block_index": i,
                            "pdf_page": raw[i]["page_idx"] + 1}
                     for key, i in rules["metadata_blocks"].items()},
        "printed_page_labels_raw": [{"pdf_page": b["page_idx"] + 1,
                                     "label": b["text"], "verified": False}
                                    for b in raw if b["type"] == "page_number"],
        "citation_policy": "pdf_page is physical, one-based; bbox_raw is not PDF points",
        "normalization_policy": "Only raw_text is source quotation; clean_text/text is derived",
        "table_positions": "zero-based row and expanded column; bbox is whole table",
    }
    return {"manifest": manifest, "blocks": blocks, "spans": list(spans.values()),
            "tables": tables, "units": units, "assets": assets, "ledger": ledger, "report": report}


def write_outputs(result: dict, output: Path, rules_bytes: bytes):
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ("blocks", "spans", "units", "ledger"):
        files[name + ".jsonl"] = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in result[name])
    for name in ("tables", "assets", "report"):
        files[name + ".json"] = json.dumps(result[name], ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    lines = ["# 清洗结果预览", "", "检索文本经过格式规范化，不是原文引句；引用应通过 spans.jsonl 回到原 PDF。", ""]
    for unit in result["units"]:
        lines += [f"## {unit['id']}", "", f"PDF 页：{unit['pages']}；类型：{unit['kind']}；可索引：{unit['indexable']}", "",
                  unit["text"], "", "必须补齐：" + (", ".join(unit["requires"]) or "无"), ""]
        if unit.get("conflict_detail"):
            lines += ["原文冲突：" + unit["conflict_detail"], ""]
        if unit["quality_flags"]:
            lines += ["待复核：" + ", ".join(unit["quality_flags"]), ""]
    files["preview.md"] = "\n".join(lines)
    report = result["report"]
    files["README.md"] = f"""# 清洗产物

由 `python -m insuretutor.ingest.clean` 离线生成；不要手改生成文件。
规则位于 `data/cleaning-rules.json`，原始文件保持不变。

- `blocks.jsonl`：保留的文本块、规范化文本、原文、页码和质量标记。
- `spans.jsonl`：可追溯原文片段，包括表格单元格和精确子串；引用使用 raw_text。
- `tables.json`：9 张表的原 HTML、单元格、展开后的合并格网格、原有题注。
- `units.jsonl`：{report['retrieval_units']} 个检索单元，其中 {report['indexable_units']} 个可进入检索。
- `ledger.jsonl`：所有 380 块的处理去向；排除仅影响派生产物。
- `assets.json`：图像/图表保留记录，不假定图片都是装饰。
- `report.json`：计数、缺字、未配对内容、原文冲突、审核范围。
- `preview.md`：方便人工阅读的规范化检索文本。
- `manifest.json`：来源哈希、产物哈希、版本号、引用约定。

接入 RAG 时只索引 `indexable=true` 的 unit，按 evidence_group 去重。
命中后必须递归补齐 requires；可调用 `expand_required(units, selected_ids)`。
依赖片段不与主条款争抢 top-k，不可截断必需条件。
质量标记和 conflict_detail 必须传给回答层，不能只取 text。
同主题双语保留在同一单元，各自来源 span 独立；未声明翻译等价。
缺字显示为 `[解析缺字]`，未猜字修订。公式碎片保留但不进入索引。
未提供简体自动转换；后续可在检索侧使用项目已有 OpenCC 依赖生成别名。

当前状态：完成结构清洗，仍有显式待复核项；不是全篇无误认证。
"""
    for name, text in files.items():
        (output / name).write_bytes(text.encode("utf-8"))
    manifest = dict(result["manifest"], rules_sha256=digest(rules_bytes),
                    cleaner_sha256=digest(Path(__file__).read_bytes()),
                    artifacts={name: digest(text.encode("utf-8")) for name, text in files.items()})
    (output / "manifest.json").write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/cleaned")
    args = parser.parse_args()
    target = args.output.resolve()
    raw_root = (ROOT / "raw data").resolve()
    if target == ROOT or target == raw_root or raw_root in target.parents:
        parser.error("Output must be separate from the repository root and raw data")
    rules_bytes = RULES.read_bytes()
    result = build(RAW.read_bytes(), json.loads(rules_bytes), PDF.read_bytes())
    write_outputs(result, target, rules_bytes)
    print(json.dumps({k: result["report"][k] for k in
                      ("input_blocks", "tables", "retrieval_units", "indexable_units", "required_edges")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
