# Data Provenance

## Source

| Field | Value |
|---|---|
| File | `FLEXI-ULife Prime Saver.pdf` |
| Size | 8,013,909 bytes (7.64 MB) |
| Pages | 20 |
| Language | Traditional Chinese + English (interleaved, page-by-page parallel) |
| Publisher | YF Life Insurance International Ltd. 萬通保險 |
| Document type | Universal life insurance product brochure |
| Print date (per brochure) | January 2022 |

## Extract

| Field | Value |
|---|---|
| Tool | `mineru-open-api` v0.5.9 (official MinerU cloud API CLI) |
| Model | MinerU VLM (server-side, fine-tuned) |
| Backend | mineru.net cloud (`api/v4`) |
| Format | `md,json` |
| OCR flag | `--ocr` |
| Timeout | 1800 s |
| Output | `raw data/mineru-official/` |

Command:

```powershell
mineru-open-api extract 'FLEXI-ULife Prime Saver.pdf' `
  -o 'raw data/mineru-official' -f md,json --timeout 1800 -v
```

### Why the official API

The self-hosted path (`mineru-kit` + own VLM endpoint) was attempted first and
abandoned — not from preference, but because the two implementations do not share a
contract.

`mineru-kit`'s VLM client sends literal prompts (`"\nText Recognition:"`,
`"\nLayout Detection:"`) and expects a **fine-tuned** model that returns structured
output containing MinaMark markers (`<|ref|>`, `<|det|>`). A general-purpose
OpenAI-compatible VLM answers those four-word prompts conversationally, and the
client rejects the response at `http_client.py:359`
(`No choices found in the response.`). This is a format-contract mismatch, not a
transient failure — retrying does not help, and the failure raises outside the HTTP
retry layer, so it is fatal rather than retried.

The official API is the same model family served by the vendor, so the contract holds
natively. The self-hosted install is retained for future work with a purpose-tuned
model.

### Upload timeout

The first attempt failed with `upload ... context deadline exceeded`. The default
`--timeout` is 300 s; uploading 7.64 MB to the OSS endpoint took ~228 s on a good run
and exceeded 300 s under load. `--timeout 1800` resolves it. `Test-NetConnection` to
the OSS host confirmed 443 was reachable — the problem was never connectivity.

## Verified output

Checked against the PDF, not against a prior parse:

| Metric | Value |
|---|---|
| Markdown size | 39,325 characters |
| Traditional Chinese characters | 5,996 |
| Latin letters | 23,136 (~3,326 English words) |
| Headings | 72 (49 CN / 23 EN, paired) |
| Tables | 9 (59 `<tr>`, 115 `<td>`) |
| Images | 42 files, 2.5 MB total, referenced as separate `.jpg` |
| Mojibake (U+FFFD) | 0 |

Spot-checks that passed — these are the values citations will rest on:

- `保證可保權益` … `最高為行使權益前基本保障額的25%` … `最多只可行使兩次`
- `保單增值權益有效至受保人51歲的保單週年日止`
- `每月提款金額最低為500美元/4,000港元/4,000澳門元，提款年期最短一年`
- `2.5% long-term guaranteed interest rate` / `Current assumed rate` (footnote \*)
- All 10 numbered notes present in **both** CN and EN, in parallel

### Reproducibility note

An earlier local parse (`mineru-kit`, same PDF) produced good English but garbled
Chinese, which was initially misread as a defect in the PDF's text layer
(no `/ToUnicode` tables). **The official parse disproves this** — the text layer is
intact and the CN came through cleanly. The local garbling was a configuration/model
problem on the self-hosted path. Recorded here so the wrong explanation does not get
inherited by anyone reading this repo later.

### Formatting caveat

Rendering this Markdown in a **GBK / CP936 Windows console** shows the Chinese as
`���x�`. That is the terminal's code page, not the file. Read it with a UTF-8 viewer
(including the Claude Code Read tool, VS Code, or `Get-Content -Encoding utf8`).
