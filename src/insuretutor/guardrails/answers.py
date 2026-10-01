"""Output structure and current-turn citation provenance only.

Answer quality, completeness, quantities and safety wording are model/eval concerns.
"""

from __future__ import annotations

import re

from opencc import OpenCC

from insuretutor.agent_tools import EvidenceSearchSession
from insuretutor.chat_models import Citation, DraftAnswer


class AnswerRejected(ValueError):
    claim_index: int | None = None
    issues: tuple[dict, ...] = ()


MESSAGES = {
    "purchase": (
        "I can explain this brochure, but cannot recommend a personal purchase.",
        "我可以解释本册，但不能提供个体购买建议。",
    ),
    "returns": (
        "Illustrations and non-guaranteed rates are not promises of future returns.",
        "示例及非保证利率不构成未来收益承诺。",
    ),
    "eligibility": (
        "Unrecorded eligibility or actual claim entitlement cannot be determined from this brochure; confirm with the insurer or a licensed adviser.",
        "本册未记载的投保资格或实际理赔资格无法据此认定，请向保险公司或持牌顾问确认。",
    ),
    "scope": (
        "I can only explain this brochure; other products and unrecorded terms are outside its scope.",
        "我只解释本册；其他产品及未记载条款超出本册范围。",
    ),
    "insufficient": (
        "The available brochure evidence is insufficient to answer this part.",
        "现有宣传册证据不足以回答这一部分。",
    ),
    "conflict": (
        "The cited sources disagree. Both versions are shown; neither is selected as authoritative. Confirm with the insurer.",
        "已引用来源存在差异，双方原文均已列出；不选择任一版本为权威，请向保险公司确认。",
    ),
    "calculation": (
        "This is a brochure-based illustration, not a determination of actual claim entitlement. Formula references were checked; model-provided inputs and arithmetic were not independently verified.",
        "这是按宣传册公式作出的算例，并非实际理赔资格认定；已核对公式引用；模型提供的输入与计算未独立核验。",
    ),
    "reset": (
        "Conversation context was reset (expired, evicted or unknown session).",
        "会话上下文已重置（已过期、被清理或会话不存在）。",
    ),
    "user_condition": ("User-provided condition:", "用户给定条件："),
    "application": ("Based on the user-provided conditions:", "按用户给定条件："),
    "excerpts": (
        "Source excerpt mode: no generated answer was accepted. The following is original brochure text, not a personalized answer.",
        "原文摘录模式：未采用生成答案。以下为宣传册原文，不是针对个人情况的回答。",
    ),
}


def message(code: str, language: str) -> str:
    text = MESSAGES[code][0 if language == "en" else 1]
    return OpenCC("s2t").convert(text) if language == "zh-Hant" else text


class EvidenceRegistry:
    """Only evidence actually delivered in this turn, without merging rankings."""

    def __init__(self, session: EvidenceSearchSession):
        self.units, self.spans, self.context, self.peers, self.conflicts = {}, {}, {}, {}, set()
        for bundle in session.bundles:
            self.units.update({u.id: u for u in bundle.units})
            self.spans.update({s.id: s for s in bundle.source_spans})
            self.context.update(bundle.context_by_unit)
            self.peers.update(bundle.parallel_units)
            self.conflicts.update(bundle.conflicts)

    def closure(self, ids: list[str]) -> list[str]:
        out = []
        pending = list(reversed(ids))
        while pending:
            uid = pending.pop()
            if uid in out:
                continue
            if uid not in self.units:
                raise AnswerRejected("unknown_or_missing_evidence")
            out.append(uid)
            u = self.units[uid]
            pending.extend(reversed(u.requires + self.peers.get(uid, [])))
        return out

    def span_ids(self, uid: str) -> list[str]:
        u = self.units[uid]
        return list(
            dict.fromkeys(u.source_span_ids + u.context_span_ids + self.context.get(uid, []))
        )

    def evidence_text(self, ids: list[str]) -> str:
        sids = dict.fromkeys(s for uid in self.closure(ids) for s in self.span_ids(uid))
        if any(s not in self.spans for s in sids):
            raise AnswerRejected("missing_source")
        return "\n".join(self.spans[s].evidence_text for s in sids)

    def citations(self, ids: list[str], language: str) -> list[Citation]:
        ids = self.closure(ids)
        span_units: dict[str, list[str]] = {}
        for uid in ids:
            u = self.units[uid]
            both = u.conflict or uid in self.conflicts
            for sid in self.span_ids(uid):
                if sid not in self.spans:
                    raise AnswerRejected("missing_source")
                s = self.spans[sid]
                if both or s.language == ("en" if language == "en" else "zh-Hant"):
                    span_units.setdefault(sid, []).append(uid)
        result = []
        for sid, owners in span_units.items():
            s = self.spans[sid]
            source_id = sid.split("/", 1)[0]
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", source_id):
                raise AnswerRejected("invalid_source_id")
            result.append(
                Citation(
                    unit_ids=owners,
                    span_id=s.id,
                    quote=s.evidence_text,
                    pdf_page=s.pdf_page,
                    language=s.language,
                    source_id=source_id,
                    source_url=f"/sources/{source_id}.pdf#page={s.pdf_page}",
                    bbox_raw=s.bbox_raw,
                    text_origin=s.text_origin,
                    origin_span_id=getattr(s, "origin_span_id", None),
                    origin_ranges=getattr(s, "origin_ranges", []),
                    bbox_precision=getattr(s, "bbox_precision", None),
                    quality_flags=s.quality_flags,
                )
            )

        return result


def validate_answer(draft: DraftAnswer, registry: EvidenceRegistry, language: str):
    """Check existing references and format presentation; never inspect answer meaning.

    Empty evidence_ids are allowed. A valid ID does not prove that the cited source
    supports the claim. That relationship and missing citations belong to evals.
    """
    draft = draft.model_copy(deep=True)
    issues = []
    for index, claim in enumerate(draft.claims):
        references = [("evidence_ids", claim.evidence_ids)]
        if claim.calculation:
            references.append(("calculation.formula_id", [claim.calculation.formula_id]))
        for field, ids in references:
            try:
                # Resolve all explicitly referenced units, required notes and contexts.
                registry.evidence_text(ids)
            except AnswerRejected as error:
                issues.append(
                    {
                        "issue": str(error),
                        "path": ["claims", index, field],
                        "claim_number": index + 1,
                        "evidence_ids": ids,
                    }
                )
        if claim.kind == "boundary":
            claim.text = message(claim.boundary, language)
        elif claim.kind == "user_condition":
            claim.text = message("user_condition", language) + " " + "; ".join(claim.user_inputs)
        elif claim.kind == "application":
            claim.text = message("application", language) + " " + claim.text
    if issues:
        error = AnswerRejected(issues[0]["issue"])
        error.claim_index = issues[0]["path"][1]
        error.issues = tuple(issues)
        raise error
    if language in {"zh-Hans", "zh-Hant"}:
        convert = OpenCC("t2s" if language == "zh-Hans" else "s2t").convert
        for claim in draft.claims:
            claim.text = convert(claim.text)
            if claim.calculation:
                claim.calculation.steps = convert(claim.calculation.steps)
                claim.calculation.result = convert(claim.calculation.result)
        if draft.clarification_question:
            draft.clarification_question = convert(draft.clarification_question)
    return draft
