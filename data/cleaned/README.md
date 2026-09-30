# 清洗产物

由 `python -m insuretutor.ingest.clean` 离线生成；不要手改生成文件。
规则位于 `data/cleaning-rules.json`，原始文件保持不变。

- `blocks.jsonl`：保留的文本块、规范化文本、原文、页码和质量标记。
- `spans.jsonl`：可追溯原文片段，包括表格单元格和精确子串；引用使用 raw_text。
- `tables.json`：9 张表的原 HTML、单元格、展开后的合并格网格、原有题注。
- `units.jsonl`：137 个检索单元，其中 135 个可进入检索。
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
