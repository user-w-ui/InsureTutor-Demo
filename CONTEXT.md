# InsureTutor

InsureTutor explains a fixed insurance brochure through cited evidence.
It distinguishes document explanations from personalized insurance advice.

## Language

**Source span / 原文片段**:
An occurrence of original text or a table row, in its own language and on its own page.
Use `evidence_text` for citations; PDF-verified corrections retain the original MinerU
text, source blocks, and physical page, and are checked against the PDF rather than
against a substring of the extraction.
_Avoid_: translation, answer, fact

**Evidence group / 证据组**:
Source spans about the same benefit or clause, which may agree or conflict.
_Avoid_: equivalent translations, canonical fact

**Qualifying note / 限定脚注**:
A note adding eligibility, limits, fees, or other conditions to a referenced benefit.
_Avoid_: optional context, decorative footnote

**Evidence bundle / 检索证据集合**:
Units and bilingual source spans returned by one retrieval, with required notes,
headers, exceptions and disagreements. A turn's registry retains the delivered bundles;
retrieval does not certify that they answer every part of the question.
_Avoid_: conversation history, model knowledge

**Source conflict / 原文冲突**:
A disagreement between passages on the same subject that a human has confirmed against
the source. Reviewed, not inferred.
_Avoid_: OCR error, inferred correction

**Citation / 引用**:
A reference from an answer to an original source span the reader can inspect.
_Avoid_: proof of correctness, similarity score

**Physical PDF page / PDF 物理页码**:
The page's position in the PDF, counting from one and including the cover. Always
equals `page_idx + 1`. This is the page anchor; original source IDs and character
ranges provide text provenance, while verified bbox geometry locates blocks or whole tables.
_Avoid_: printed page number, zero-based page index

**Printed page number / 印刷页码**:
The label printed inside the brochure, verified against the original page.
MinerU's `page_number` is only a candidate: on physical page 6 it extracted the
section number 1, but the actual printed page number is 5. Store raw labels and
verified labels separately; never compute unverified labels by offset.
_Avoid_: PDF physical page, page_idx offset

**Curation / 人工审核记录**:
The committed, hand-authored input that declares note labels, note links, and reviewed
conflicts. Finite PDF-verified corrections live in `data/cleaning-rules.json` with
source blocks and physical pages; frozen source files are never altered.
_Avoid_: OCR output, machine-inferred link, unverified judgement

**Document explanation / 资料解释**:
A description of what the supplied brochure says, including its conditions and limits.
_Avoid_: personalized purchase recommendation, claim decision

**Extractive response / 原文摘录回答**:
A labeled presentation of source passages without generated synthesis.
_Avoid_: generated tutoring, unsupported fallback answer
