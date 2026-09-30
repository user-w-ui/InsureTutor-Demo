# 清洗结构映射

输入 JSON SHA-256：`23b55338c73de0e8052e2eb83225434e10f3956f24667f4d19fb2add4f1dbbf3`。索引均从 0 开始。由 Codex 核对，非人工签字；同主题配对不保证逐字等价。

## 九张表

| block | PDF 页 | 原生 caption | 表头行 | 关联附注 |
| --- | --- | --- | --- | --- |
| 97 | 7 | 无，不补造 | [0] | {'1': [4], '3': [5]} |
| 114 | 8 | 无，不补造 | [0] | {} |
| 150 | 9 | 无，不补造 | [0] | {} |
| 231 | 13 | 无，不补造 | [0] | {} |
| 252 | 13 | 无，不补造 | [0] | {} |
| 352 | 16 | 无，不补造 | [] | {'8': [3], '9': [8], '10': [9]} |
| 354 | 17 | 无，不补造 | [] | {'6': [10], '7': [10], '8': [10]} |
| 356 | 18 | 保單資料 Policy Information | [] | {'0': [10], '1': [6, 7, 10]} |
| 357 | 18 | 投保資料 Basic Information | [] | {} |

## 编号附注

| 编号 | 中文 block | 英文 block | 关联正文组 |
| --- | --- | --- | --- |
| 1 | 197 | 208 | generic-coverage, coverage-change |
| 2 | 198 | 209 | enhancement-summary, enhancement |
| 3 | 199 | 210 | enhancement-summary, insurability, life-stage-example |
| 4 | 200 | 211 | level-summary |
| 5 | 201 | 212 | incremental-summary |
| 6 | 202 | 213 | withdrawal-summary, withdrawal |
| 7 | 203 | 214 | withdrawal |
| 8 | 204 | 215 | unemployment-summary, unemployment |
| 9 | 205 | 216 | terminal-illness |
| 10 | 206 | 217 |  |

第 8 页局部 `*`、`^`、`#` 分别映射到 rate-date-note、interest-year20-note、interest-every5-note。

第 7 页身故保障表裸数字对应附注 4、5；附注 3 对应保證可保權益正文及第 16 页摘要表，不能混为同一关联。

机器可读的详细结构、准确字面匹配、双语组及强制关系见 [cleaning-rules.json](../data/cleaning-rules.json)。

有限的 PDF 校对补丁和分栏片段也记录在 cleaning-rules.json：来源块、物理页、修订文本及理由均可查。原有 7 项文本问题已解决；额外回报、算例和现金价值公式已恢复。修订引句按 PDF 核对，不要求是 MinerU 原块的连续子串。第 16 页粘连子行仍按精确子串分开，第 17 页冲突保留。后续切块入口是 data/cleaned/units.jsonl。
