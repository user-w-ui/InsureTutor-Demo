# 清洗产物

由 `python -m insuretutor.ingest.clean` 离线生成；不要手改生成文件。
规则位于 `data/cleaning-rules.json`，原始文件保持不变。

- `blocks.jsonl`：保留的文本块、规范化文本、原文、页码和质量标记。
- `spans.jsonl`：来源片段及 PDF 校对文本；引用使用 evidence_text，text_origin 区分两者。
- `tables.json`：9 张表的原 HTML、单元格、展开后的合并格网格、原有题注。
- `units.jsonl`：137 个干净片段，其中 137 个可用于后续切块和检索。
- `ledger.jsonl`：所有 380 块的处理去向；排除仅影响派生产物。
- `assets.json`：图像/图表保留记录，不假定图片都是装饰。
- `report.json`：计数、缺字、未配对内容、原文冲突、审核范围。
- `preview.md`：方便人工阅读的规范化检索文本。
- `manifest.json`：来源哈希、产物哈希、版本号、引用约定。

条款、附注、表格行保持独立，最终 chunk 和索引由后续 RAG 步骤完成。
后续使用 `indexable=true` 的片段，按 evidence_group 去重。
命中后必须递归补齐 requires；可调用 `expand_required(units, selected_ids)`。
依赖片段不与主条款争抢 top-k，不可截断必需条件。
质量标记和 conflict_detail 必须传给回答层，不能只取 text。
同主题双语关联；已校对分栏提供 segments，分别保存语言、标题和正文。
原有 7 项问题已按原 PDF 修复，未解决项 0。
额外回报、算例和现金价值公式已恢复。修订有来源块、物理页码及理由。
修订引句核对 PDF；raw_text 是原始解析记录，不能用它的子串匹配否定已核对的修订。
未提供简体自动转换；后续可在检索侧使用项目已有 OpenCC 依赖生成别名。

原始文件冻结，生成文件覆盖当前版本，不保存历史版本。第 17 页原文金额冲突仍保留。
