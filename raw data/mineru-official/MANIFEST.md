# MANIFEST — MinerU official API output

**Verbatim tool output. Do not hand-edit anything under `content/`.**
Regeneration wipes this tree.

The only post-processing applied: the tool's output was flattened one level, so
`content/` holds the `.md`, the `.json`, and the `images/` folder **as siblings**.
Nothing inside the artifacts was edited, so the `images/<hash>.jpg` references in
both files resolve relative to the artifact and open in any Markdown viewer.

| Field | Value |
|---|---|
| Source | `FLEXI-ULife Prime Saver.pdf` — 8,013,909 bytes, 20 pages |
| Tool | `mineru-open-api` v0.5.9 — official MinerU cloud API CLI |
| Backend | mineru.net `api/v4`, `model_version: vlm` |
| Flags | `-f md,json --timeout 1800` |
| Extracted | 2026-09-29 18:31 (+08:00) |
| Credential | `MINERU_TOKEN` env var — not stored here |

## Contents

```
mineru-official/
├── content/
│   ├── FLEXI-ULife Prime Saver.md    39k chars — prose, 72 headings, 9 HTML tables
│   ├── FLEXI-ULife Prime Saver.json  86 KB — 380 blocks, page + bbox anchors
│   └── images/*.jpg                  42 figures, 2.5 MB
└── MANIFEST.md                       this file
```

### Which artifact to use for what

| Need | Use | Why |
|---|---|---|
| Page numbers, bboxes → **citation anchors** | `.json` | Markdown has no page info. A citation saying "page 7" is unverifiable against the `.md`. |
| HTML tables | `.md` | JSON table blocks hold a rasterized `img_path`; the structured `<table>` HTML lives in `table_body` but the rendered table is in the `.md`. |
| Clean prose for the index | `.json` `text` blocks | Pre-split into 298 text blocks with heading levels. |
| Figures to show in answers | `content/images/` | 42 JPEGs. |

**JSON block schema** (380 blocks):

```jsonc
// text (298), header (14), footer (8), aside_text (1) — note: 292/298 text blocks
{
  "type": "text",
  "page_idx": 6,            // 0-based — add 1 for human-facing page numbers
  "bbox": [x0, y0, x1, y1], // PDF points
  "text": "…",
  "text_level": 1           // present only on headings (72 of them: 1 or 2)
}

// table (9)
{
  "type": "table",
  "page_idx": 6,
  "bbox": [...],
  "table_body": "<table>…</table>",  // non-empty in all 9
  "table_caption": [],
  "table_footnote": [],
  "img_path": "images/<hash>.jpg"
}

// image (32) / chart (1)
{ "type": "image", "page_idx": ..., "bbox": [...], "img_path": "images/<hash>.jpg",
  "image_caption": [], "image_footnote": [] }
```

Other types: `page_number` (16), `header` (14), `footer` (8), `page_footnote` (1),
`aside_text` (1). **Filter these out before indexing** — page numbers and running
headers are noise, and `page_number` blocks are literally just digits.

## Image paths

MinerU writes `.md`, `.json`, and `images/` as **siblings** in one output directory,
and references each figure as `images/<hash>.jpg` — a path relative to the artifact.
That layout is preserved here on purpose: leave `images/` next to the `.md` and every
link resolves, in the Markdown viewer and in code, with no remapping step.

So there is **nothing to remap** — `images/foo.jpg` is already correct relative to
`content/`. Do not move `images/` out of `content/`; if you do, all 33 in-prose links
break in any Markdown viewer.

Note the two counts differ legitimately: the `.md` inlines 33 figures, the `.json`
carries 42 `img_path` entries. The extra 9 are the rasterized table crops — the
structured `<table>` HTML is the authoritative form of those, so they are not inlined
into the prose.

## Known gaps

- **Table captions and footnotes are empty arrays** in JSON. The prose captions
  (`例子 Example`, etc.) survive as separate `text` blocks, but the attachment is lost —
  the ingest step has to re-associate by `page_idx` + proximity.
- **Table structures are also rasterized** (`img_path`). The `table_body` HTML is the
  authoritative structured form; the image is a cross-check.
- `page_idx` is **0-based**. Every human-facing citation needs `+1`.

## Integrity check

From the repo root:

```powershell
python -c "
import json,re
d=json.load(open('raw data/mineru-official/content/FLEXI-ULife Prime Saver.json',encoding='utf-8'))
md=open('raw data/mineru-official/content/FLEXI-ULife Prime Saver.md',encoding='utf-8').read()
print('blocks',len(d),'| pages',max(b[\"page_idx\"] for b in d)+1)
print('CJK in md',len(re.findall(r'[一-鿿]',md)),'| U+FFFD in md',md.count(chr(0xFFFD)))
print('tables',sum(1 for b in d if b['type']=='table'),'| images',sum(1 for b in d if b['type'] in('image','chart')))
"
```

Expected for this run: `blocks 380 | pages 20`, `CJK in md 5986 | U+FFFD in md 0`,
`tables 9 | images 33`.

CJK count is an **exact-match** check only against this specific extract. A re-parse
may legitimately differ by a few characters (an earlier run with `--ocr` produced
5,996). U+FFFD staying at 0 is the invariant that matters.

> **Windows console caveat.** A GBK/CP936 console renders this Chinese as `���x�`.
> That is the terminal's code page, not the file. The files are UTF-8 and verified
> correct by codepoint. Use VS Code, the Read tool, or `Get-Content -Encoding utf8`.
