"""Deterministic provenance/number checks, not semantic or arithmetic verification."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from opencc import OpenCC

from insuretutor.agent_tools import EvidenceSearchSession
from insuretutor.chat_models import Citation, Claim, DraftAnswer

_CC = OpenCC("t2s")
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?"
_CURRENCY = r"us\$|usd|hk\$|hkd|mop\$?|美元|港元|澳门元"
FORMULAS = {
    "table-97-row-1": "max(account_value,basic_sum_insured-recent_withdrawals)",
    "table-97-row-2": "account_value+basic_sum_insured",
    "table-97-row-3": "max(account_value,basic_sum_insured+0.5*account_value-0.5*recent_withdrawals)",
}


class AnswerRejected(ValueError):
    draft: DraftAnswer | None = None
    claim_index: int | None = None
    unsupported_quantities: tuple[tuple[str, str], ...] = ()


def normalized(text: str) -> str:
    text = _CC.convert(unicodedata.normalize("NFKC", text)).lower()
    text = text.replace("\\$", "$").replace("\\%", "%")
    text = re.sub(r"\b(?:us\s+dollars?|u\.s\.\s+dollars?)\b", "usd", text)
    text = re.sub(r"\b(?:hk|hong kong)\s+dollars?\b", "hkd", text)
    text = re.sub(r"\b(?:macau\s+)?patacas?\b", "mop", text)
    text = re.sub(r"\b(us|hk)\s+\$", r"\1$", text)
    text = re.sub(r"\b(?:per\s+cent|percent)\b", "%", text)
    # Only convert written Chinese numbers next to quantitative units.
    chars = "零〇一二两三四五六七八九十百千万亿"

    def cn_number(match):
        digits = dict(zip("零〇一二两三四五六七八九", [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
        total = section = number = 0
        for char in match[1]:
            if char in digits:
                number = digits[char]
            else:
                unit = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}[char]
                if unit < 10000:
                    section += (number or 1) * unit
                else:
                    total += (section + number) * unit
                    section = 0
                number = 0
        return str(total + section + number)

    text = re.sub(rf"百分之([{chars}]+)", lambda m: cn_number(m) + "%", text)
    text = re.sub(
        rf"(?<![0-9{chars}])([{chars}]+)(?=\s*(?:年|个月|月|岁|次|天|美元|港元|澳门元|%))",
        cn_number,
        text,
    )
    text = re.sub(r"百分之(\d+(?:\.\d+)?)", r"\1%", text)
    for word, digit in (
        ("eleven", "11"),
        ("ten", "10"),
        ("three", "3"),
        ("two", "2"),
        ("one", "1"),
    ):
        text = re.sub(rf"\b{word}(?=\s+(?:years?|months?|times?|days?))", digit, text)
    text = re.sub(r"\btwice\b", "2 times", text)
    return text


def _amount(raw: str, scale: str = "") -> str:
    factor = {"万": 10000, "亿": 100000000, "million": 1000000, "thousand": 1000}.get(scale, 1)
    return str((Decimal(raw.replace(",", "")) * factor).normalize())


def quantities(text: str) -> set[tuple[str, str]]:
    """Keep number, percent and currency associations distinct across languages."""
    text = normalized(text)
    out: set[tuple[str, str]] = set()
    scale = r"(?:万|亿|million|thousand)?"
    # Plain numbers also support user inputs, dates and policy durations.
    for m in re.finditer(rf"({_NUMBER})\s*({scale})", text):
        out.add(("number", _amount(m[1], m[2])))
    for m in re.finditer(rf"({_NUMBER})\s*%", text):
        out.add(("percent", _amount(m[1])))
    currencies = {
        "us$": "USD",
        "usd": "USD",
        "美元": "USD",
        "hk$": "HKD",
        "hkd": "HKD",
        "港元": "HKD",
        "mop": "MOP",
        "mop$": "MOP",
        "澳门元": "MOP",
    }
    for pattern, before in (
        (rf"({_CURRENCY})\s*({_NUMBER})\s*({scale})", True),
        (rf"({_NUMBER})\s*({scale})\s*({_CURRENCY})", False),
    ):
        for m in re.finditer(pattern, text):
            cur, num, mul = (m[1], m[2], m[3]) if before else (m[3], m[1], m[2])
            out.add((currencies[cur], _amount(num, mul)))
    return out


def claim_quantities(text: str, source: str) -> set[tuple[str, str]]:
    """Distinguish narrative 'first/once' from numerical limits and amounts.

    Chinese 第一次 is equivalent to English 'first', which is already prose
    rather than a digit. A distribution described as once per period is allowed
    only when that exact period is explicitly stated in the cited sources.
    """
    text, source = normalized(text), normalized(source)
    text = re.sub(r"第1次", "首次", text)

    def cadence(match):
        interval, unit = match[1], match[2]
        english = {"年": "years?", "月": "months?", "天": "days?"}[unit]
        if re.search(
            rf"每\s*{re.escape(interval)}\s*{unit}|every\s+{re.escape(interval)}\s+{english}\b",
            source,
        ):
            return match[0].replace("1次", "")
        return match[0]

    text = re.sub(rf"每({_NUMBER})(年|月|天)(?:派发|发放|支付|拨入)?1次", cadence, text)
    # 'One of the distributions' identifies an event, rather than imposing a
    # one-time limit; require a sourced recurring-distribution clause as well.
    if re.search(r"每\s*\d+\s*(?:年|月|天)|every\s+\d+\s+(?:years?|months?|days?)\b", source):
        text = re.sub(r"其中1次(?=派发|发放|支付|拨入)", "其中的", text)
    return quantities(text)


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
        "This is a brochure-based illustration, not a determination of actual claim entitlement. Inputs and formula sources were checked; arithmetic was not independently recomputed.",
        "这是按宣传册公式作出的算例，并非实际理赔资格认定；已核对输入和公式来源，未独立复算结果。",
    ),
    "reset": (
        "Conversation context was reset (expired, evicted or unknown session).",
        "会话上下文已重置（已过期、被清理或会话不存在）。",
    ),
    "user_condition": ("User-provided condition:", "用户给定条件："),
    "application": ("Based on the user-provided conditions:", "按用户给定条件："),
    "medical": (
        "This brochure does not record hospital medical-expense reimbursement terms.",
        "本册未记载住院医疗费用报销条款。",
    ),
    "travel": ("This brochure does not record travel-insurance cover.", "本册未记载旅游保险保障。"),
    "motor": ("This brochure does not record motor-insurance cover.", "本册未记载汽车保险保障。"),
    "ownership_question": (
        "Do you already hold this policy, or are you considering a new application?",
        "你已经持有本册计划的保单，还是准备新投保？",
    ),
    "excerpts": (
        "Source excerpt mode: no generated answer was accepted. The following is original brochure text, not a personalized answer.",
        "原文摘录模式：未采用生成答案。以下为宣传册原文，不是针对个人情况的回答。",
    ),
    "partial": (
        "Some content could not be verified and has been omitted with related claims. Only the remaining source-checked paragraphs are shown; this is an incomplete answer.",
        "部分内容未能通过校验，已连同关联段落省略。以下仅保留其余通过来源校验的段落，回答并不完整。",
    ),
}


def message(code: str, language: str) -> str:
    text = MESSAGES[code][0 if language == "en" else 1]
    return OpenCC("s2t").convert(text) if language == "zh-Hant" else text


def check_scope(text: str, user_text: str = ""):
    """Conservative phrase checks complement the fixed model policy and evals."""
    t = normalized(text)
    patterns = (
        r"(?:建议|推荐|适合|应该|应当|最好).{0,12}(?:你|您).{0,12}(?:购买|投保|买)",
        r"(?:你|您).{0,12}(?:应该|应当|适合|最好).{0,12}(?:购买|投保|买)",
        r"\b(?:you should buy|i recommend|suitable for you|best for you|you should purchase)\b",
        r"\b(?:i suggest (?:buying|choosing)|you ought to buy|this plan is perfect for you)\b",
        r"(?:推荐|建议)(?:购买|投保|买入)|(?:稳赚|包赚|保本保息)",
        r"\b(?:you are eligible|you will receive (?:a |the )?payout|your claim will be paid)\b|(?:你|您)(?:符合投保资格|一定获赔|必然获赔)",
        r"(?:system prompt|api[_ -]?key|系统提示|密钥)\s*[:：=]",
        r"https?://|file://|/sources/|raw data[/\\]|#page=",
        r"ignore (?:all |the |previous )?(?:instructions|rules|policy)|忽略.{0,8}(?:指令|规则|政策)",
        r"<\s*/?\s*(?:system|developer|assistant)\b|\[\s*(?:system|developer)\s*\]",
    )
    # Negated policy statements are produced by the server boundary codes; the
    # factual channel remains deliberately conservative.
    if any(re.search(p, t) for p in patterns):
        raise AnswerRejected("scope_violation")
    for pattern in (
        r"(?:保证|确保|必定|一定).{0,12}(?:收益|回报|赚钱|获利)",
        r"\b(?:guaranteed returns?|will definitely earn|guarantee (?:a |your )?return)\b",
        r"\breturns? (?:is|are|will be) guaranteed\b",
    ):
        for match in re.finditer(pattern, t):
            prefix = t[max(0, match.start() - 16) : match.start()]
            if not re.search(
                r"(?:not |non[- ]|no |cannot |can't |不|非|未|无法|不能|不是|并非)$", prefix
            ):
                raise AnswerRejected("scope_violation")
    if re.search(
        r"居留|国籍|居民|resident|nationality|citizenship", normalized(user_text)
    ) and re.search(
        r"(?:你|您|非香港居民).{0,12}(?:可以投保|能投保|符合资格)|\b(?:you (?:can|may) (?:apply|buy)|eligible to apply|non.residents? can)\b",
        t,
    ):
        raise AnswerRejected("unrecorded_eligibility")


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


# Positive statements that the user already holds a policy. This suppresses the
# ownership question, so it holds only affirmative ownership. Phrases announcing a
# NEW application ("新买", "准备投保") and phrases denying ownership ("没有保单") are
# excluded on purpose: both are exactly the case where ownership still has to be
# settled, and treating "I do not hold this policy" as settled would ask nothing.
STATES_POLICY_OWNERSHIP = re.compile(
    r"已有保单|已持有|已投保|已经买|已购买|我份保单|我的保单|手上.{0,6}保单|"
    r"保单.{0,15}(?:生效|在供|供了|已缴)|已供|"
    r"\b(?:already (?:hold|have|own|bought|purchased)|existing policy|in force|"
    r"my policy|i (?:hold|own|have) (?:a|this|an) policy)\b"
)


PURCHASE_INTENT = re.compile(
    # Asking which product to buy, in any of the shapes a customer uses. Purpose
    # words (education, marriage, retirement) are deliberately absent: those are an
    # open set, and the ownership question this feeds applies to all of them alike.
    r"(?:该|应|适合|推荐|建议|投什么|买什么|买哪|買哪|買什麼|选哪).{0,12}(?:买|買|投保|保险|保險)"
    r"|要投什么|买什么好|买哪个好|"
    r"(?:想|打算|准备|计划|考虑).{0,6}(?:买|買|投保|投|購|买保险)|"
    r"\b(?:should i buy|what (?:insurance )?(?:should i )?buy|which (?:one|policy|plan)|"
    r"recommend.*(?:buy|insurance)|looking to (?:buy|insure)|want to buy|"
    r"thinking (?:about|of) (?:buying|getting))\b"
)


def required_boundaries(question: str) -> tuple[list[str], list[str]]:
    """Small fixed domain boundaries; no question splitting or extra model."""
    q = normalized(question)
    codes, topics = [], []
    if PURCHASE_INTENT.search(q):
        codes.append("purchase")
    if re.search(
        r"(?:保证|承诺).{0,15}(?:回报|收益)|(?:guarantee|promise).{0,25}(?:return|earn|interest)", q
    ):
        codes.append("returns")
    if re.search(r"住院.{0,12}(?:报销|赔)|hospital.{0,25}(?:reimburs|expenses?)", q):
        topics.append("medical")
    if re.search(r"(?:旅游|旅行|travel).{0,30}(?:出事|赔|accident|cover|insurance)", q):
        topics.append("travel")
    if re.search(r"车撞|车险|汽车保险|motor insurance|car.{0,15}(?:crash|accident)", q):
        topics.append("motor")
    if topics:
        codes.append("scope")
    return codes, topics


def selects_conflict_authority(text: str) -> bool:
    """Recognize explicit denials without letting one denial excuse another assertion."""
    text = normalized(text)
    denial = (
        r"(?:不选择|不能选择|不应选择|不能以|不应以|不以|无法认定)"
        r"(?:英文|中文)(?:版本|原文)?(?:为准|为权威|为正确版本)|"
        r"(?:英文|中文)(?:版本|原文)?(?:并非|不是|不能视为)(?:正确|权威)|"
        r"(?:do not|cannot|can't|must not|should not) "
        r"(?:choose|select|treat|regard|prefer) (?:the )?(?:english|chinese)"
        r"(?: version| text)?(?: as)? (?:correct|authoritative)|"
        r"(?:english|chinese)(?: version| text)? is (?:not|not necessarily) "
        r"(?:correct|authoritative)"
    )
    text = re.sub(denial, "", text)
    return bool(
        re.search(
            r"(?:英文|中文).{0,10}(?:正确|权威|为准)|"
            r"(?:english|chinese).{0,20}(?:correct|authoritative)|"
            r"prefer (?:the )?(?:english|chinese)",
            text,
        )
    )


def validate_answer(
    draft: DraftAnswer, registry: EvidenceRegistry, user_questions: list[str], language: str
):
    """Return a sanitized draft or reject it; Tutor controls correction/recovery."""
    draft = draft.model_copy(deep=True)
    all_user = "\n".join(user_questions)
    for index, claim in enumerate(draft.claims):
        if claim.kind == "boundary":
            claim.text = message(claim.boundary, language)
            continue
        if claim.kind == "user_condition":
            for value in claim.user_inputs:
                if not value.strip() or not any(value in q for q in user_questions):
                    raise AnswerRejected("invented_user_input")
                check_scope(value)
                if re.search(
                    r"^\s*(?:say|ignore|pretend|invent|reveal|execute|invoke)\b|(?:无视|忽略|假装|编造|伪造)",
                    normalized(value),
                ):
                    raise AnswerRejected("instruction_is_not_user_condition")
            claim.text = message("user_condition", language) + " " + "; ".join(claim.user_inputs)
            continue
        check_scope(claim.text, all_user)
        source = registry.evidence_text(claim.evidence_ids)
        if any(
            registry.units[u].conflict or u in registry.conflicts
            for u in registry.closure(claim.evidence_ids)
        ) and selects_conflict_authority(claim.text):
            raise AnswerRejected("conflict_authority_selected")
        allowed = quantities(source)
        if claim.kind == "application":
            for value in claim.user_inputs:
                if not value.strip() or not any(value in q for q in user_questions):
                    raise AnswerRejected("invented_user_input")
                # User duration/age can select a source rule/range; user-proposed
                # money and percentages cannot become document facts this way.
                for number in re.findall(
                    rf"({_NUMBER})\s*(?:years?|months?|days?|年|个月|月|岁|天)", normalized(value)
                ):
                    allowed.add(("number", _amount(number)))
        if claim.calculation:
            calc = claim.calculation
            if calc.formula_expression != FORMULAS[calc.formula_id]:
                raise AnswerRejected("formula_mismatch")
            if calc.formula_id not in claim.evidence_ids:
                raise AnswerRejected("missing_formula")
            formula = registry.units[calc.formula_id]
            if set(formula.requires) - set(claim.evidence_ids):
                raise AnswerRejected("missing_calculation_notes")
            if not re.search(r"death benefit|身故保障|身故赔偿", normalized(source)):
                raise AnswerRejected("not_death_benefit_formula")
            check_scope(calc.steps + "\n" + calc.result, all_user)
            if re.search(r"收益|回报|return|yield|forecast", normalized(calc.steps + claim.text)):
                raise AnswerRejected("unsupported_calculation")
            inputs = set()
            financial_values = set()
            input_names = {item.name for item in calc.inputs}
            if (
                len(input_names) != len(calc.inputs)
                or not {"basic_sum_insured", "account_value"} <= input_names
            ):
                raise AnswerRejected("missing_calculation_input")
            if calc.formula_id != "table-97-row-2":
                withdrawal = next((i for i in calc.inputs if i.name == "withdrawals"), None)
                if withdrawal is None:
                    raise AnswerRejected("missing_calculation_input")
                if ("number", "0") not in quantities(
                    withdrawal.user_text
                ) and "withdrawal_timing" not in input_names:
                    raise AnswerRejected("missing_withdrawal_timing")
            for item in calc.inputs:
                if not any(item.user_text in q for q in user_questions) or not quantities(
                    item.user_text
                ):
                    raise AnswerRejected("invented_calculation_input")
                inputs |= quantities(item.user_text)
                if item.name != "withdrawal_timing":
                    found = quantities(item.user_text)
                    amounts = {v for k, v in found if k in {"USD", "HKD", "MOP"}}
                    financial_values |= {
                        ("number", v)
                        for k, v in found
                        if k == "number" and (not amounts or v in amounts)
                    }
            # Formula substitutions can omit repeated currency labels. Timing is
            # verified against user text, not demanded as a literal formula term.
            if not financial_values <= quantities(calc.steps):
                raise AnswerRejected("calculation_input_omitted")
            if not quantities(calc.result):
                raise AnswerRejected("missing_calculation_result")
            input_currencies = {k for k, _ in inputs if k in {"USD", "HKD", "MOP"}}
            result_currencies = {
                k for k, _ in quantities(calc.result) if k in {"USD", "HKD", "MOP"}
            }
            if not input_currencies or result_currencies != input_currencies:
                raise AnswerRejected("calculation_currency_mismatch")
            # Derived amounts are permitted only in a marked death-benefit
            # calculation. No arithmetic evaluation or semantic guarantee here.
            allowed |= quantities(calc.steps) | quantities(calc.result) | inputs
        unsupported = claim_quantities(claim.text, source) - allowed
        if unsupported:
            error = AnswerRejected("unsupported_quantity")
            error.claim_index = index
            error.unsupported_quantities = tuple(sorted(unsupported))
            raise error
        if claim.kind == "application":
            claim.text = message("application", language) + " " + claim.text
    if draft.clarification_question:
        check_scope(draft.clarification_question, all_user)
        # Asking about a sourced threshold or an actual user figure is not an
        # invented numerical premise. Unseen numbers/units still fail closed.
        supported = quantities(all_user) | quantities(registry.evidence_text(list(registry.units)))
        if not quantities(draft.clarification_question) <= supported:
            raise AnswerRejected("numeric_assumption_in_clarification")
        if len(re.findall(r"[?？]", draft.clarification_question)) > 1:
            raise AnswerRejected("multiple_clarifications")
    codes, topics = required_boundaries(user_questions[-1])
    present = {c.boundary for c in draft.claims if c.kind == "boundary"}
    for code in codes:
        if code not in present:
            draft.claims.append(Claim(kind="boundary", text=message(code, language), boundary=code))
    if topics:
        scope = next((c for c in draft.claims if c.boundary == "scope"), None)
        if scope is None:
            # required_boundaries pairs every topic with the scope code, so this is
            # unreachable today; backfill rather than raise if that coupling changes.
            scope = Claim(kind="boundary", text=message("scope", language), boundary="scope")
            draft.claims.append(scope)
        scope.text = (
            message("scope", language) + " " + " ".join(message(t, language) for t in topics)
        )
    # A purchase question is asked on behalf of some purpose, and the purpose is an
    # open set: education, marriage, retirement, a house. Enumerating those words
    # would encode the eval fixtures into policy and miss every paraphrase, so the
    # rule keys on the shape instead - an unsourced buying intent, with no statement
    # that the user already holds this policy, needs its ownership settled first.
    if "purchase" in codes and not STATES_POLICY_OWNERSHIP.search(normalized(all_user)):
        draft.clarification_question = message("ownership_question", language)
        draft.status = "clarification"
    if language == "en":
        prose = "\n".join(
            [c.text for c in draft.claims if c.kind != "user_condition"]
            + [
                part
                for c in draft.claims
                if c.calculation
                for part in (c.calculation.steps, c.calculation.result)
            ]
            + [draft.clarification_question or ""]
        )
        han, latin = len(re.findall(r"[\u3400-\u9fff]", prose)), len(re.findall(r"[a-zA-Z]", prose))
        # English explanations may name short original Chinese product/option
        # labels. A predominantly Chinese answer still fails the explicit choice.
        if han and (latin < 20 or han > latin * 0.2):
            raise AnswerRejected("response_language_mismatch")
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


def validate_partial_answer(draft, registry, user_questions, language):
    """Recover only separate evidence groups after one unsuccessful correction.

    Provenance/quantity checks do not prove semantic independence or correctness.
    Global boundary, source, input, calculation and language failures stay closed.
    """
    failed, footprints = set(), []
    for i, claim in enumerate(draft.claims):
        try:
            validate_answer(
                DraftAnswer(status="answered", claims=[claim]), registry, user_questions, language
            )
        except AnswerRejected as exc:
            if str(exc) != "unsupported_quantity" or claim.kind != "fact":
                raise
            failed.add(i)
        footprints.append(
            {
                sid
                for uid in registry.closure(claim.evidence_ids)
                for sid in registry.span_ids(uid)
                if sid in registry.units[uid].source_span_ids
                or normalized(registry.spans[sid].evidence_text).strip(" :：")
                not in {"notes", "附注"}
            }
        )
    if not failed:
        raise AnswerRejected("unsupported_quantity")
    # Drop the whole connected component, including another paragraph's shared
    # sources, context, mandatory notes and paired conflict units.
    while True:
        affected = set().union(*(footprints[i] for i in failed))
        linked = {i for i, spans in enumerate(footprints) if spans & affected}
        if linked <= failed:
            break
        failed |= linked
    remaining = [c for i, c in enumerate(draft.claims) if i not in failed]
    if not any(c.kind in {"fact", "application", "calculation"} for c in remaining):
        raise AnswerRejected("unsupported_quantity")
    # Do not leave an explicit reference or conclusion pointing at omitted prose.
    if any(
        re.search(
            r"上述|前述|前者|后者|上文|因此|所以|因而|"
            r"\b(?:above|former|latter|therefore|consequently)\b",
            normalized(c.text),
        )
        for c in remaining
    ):
        raise AnswerRejected("unsupported_quantity")
    partial = DraftAnswer(
        status="insufficient", claims=remaining, clarification_question=draft.clarification_question
    )
    return validate_answer(partial, registry, user_questions, language)
