# InsureTutor

InsureTutor explains a fixed insurance brochure through cited evidence.
It distinguishes document explanations from personalized insurance advice.

## Language

**Source span / 原文片段**:
An occurrence of original text or a table row, in its own language and on its own page.
_Avoid_: translation, answer, fact

**Evidence group / 证据组**:
Source spans about the same benefit or clause, which may agree or conflict.
_Avoid_: equivalent translations, canonical fact

**Qualifying note / 限定脚注**:
A note adding eligibility, limits, fees, or other conditions to a referenced benefit.
_Avoid_: optional context, decorative footnote

**Evidence bundle / 本轮证据集合**:
Source spans supporting a question, with necessary notes, exceptions, and disagreements.
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
equals `page_idx + 1`. This is the only citation anchor.
_Avoid_: printed page number, zero-based page index

**Printed page number / 印刷页码**:
The label printed inside the brochure, read from that page's own `page_number` block.
Not a constant shift of the physical page: numbering starts after the cover and then
restarts, so it is metadata only and is never computed by offset.
_Avoid_: PDF physical page, page_idx offset

**Curation / 人工审核记录**:
The committed, hand-authored input that declares note labels, note links, and reviewed
conflicts. It may declare relationships; it may never supply or alter source text.
_Avoid_: OCR output, machine-inferred link, unverified judgement

**Document explanation / 资料解释**:
A description of what the supplied brochure says, including its conditions and limits.
_Avoid_: personalized purchase recommendation, claim decision

**Extractive response / 原文摘录回答**:
A labeled presentation of source passages without generated synthesis.
_Avoid_: generated tutoring, unsupported fallback answer
