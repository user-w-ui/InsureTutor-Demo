"""Small brochure-specific lexical vocabulary; never used as citation evidence."""

from __future__ import annotations

import re
from decimal import Decimal

from insuretutor.corpus import Corpus

from .embedding import normalize_search

# Verified pairs from bilingual headings. Each key is a cleaner source_key.
# At startup both phrases must still exist in the cited source fragment.
TERM_PAIRS = [
    ("b85", "保单增值权益", "policy enhancement option"),
    ("b88", "保证可保权益", "guaranteed insurability option"),
    ("b72", "定期提款权益", "automatic periodic withdrawal option"),
    ("b118", "基本派息", "base crediting interest"),
    ("b121", "额外利息", "retrospective additional interest"),
    ("b142", "额外回报", "extra bonus"),
    ("b97:r1:c0", "固定寿险保障", "level benefit"),
    ("b97:r2:c0", "递增寿险保障", "increasing benefit"),
    ("b97:r2:c0", "特级递增寿险保障", "increasing benefit plus"),
    ("b97:r3:c0", "渐进寿险保障", "incremental benefit"),
    ("b352:r9:c0", "失业保障", "unemployment benefit"),
    ("b352:r14:c0", "保单货币单位", "currency"),
    ("b352:r15:c0", "缴费方式", "payment mode"),
    ("b352:r6:c0", "利息保证", "guaranteed interest"),
]
# Standard English function words otherwise give long conversational questions
# high scores against irrelevant clauses. Keep negation and insurance vocabulary.
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "from",
        "by",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "his",
        "she",
        "her",
        "they",
        "their",
        "what",
        "which",
        "when",
        "where",
        "how",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "if",
        "as",
        "than",
        "then",
        "each",
        "please",
        "according",
        "tell",
        "about",
    ]
)
CURRENCY = {
    "us$": "usd",
    "usd": "usd",
    "美元": "usd",
    "hk$": "hkd",
    "hkd": "hkd",
    "港元": "hkd",
    "mop": "mop",
    "澳门元": "mop",
}
CJK = r"[\u3400-\u9fff]"
NUMBER = r"\d+(?:\.\d+)?"


def verified_terms(corpus: Corpus) -> list[tuple[str, str, str]]:
    spans = {}
    for source in corpus.source_spans:
        # Both language records retain the same original heading key.
        spans.setdefault(source.source_key, set()).add(
            normalize_search(source.evidence_text).lower())
    terms = []
    for key, chinese, english in TERM_PAIRS:
        if not all(any(term in text for text in spans.get(key, ())) for term in (chinese, english)):
            raise ValueError(f"Lexical bilingual heading no longer matches source {key}")
        terms.append((f"term:{key}", chinese, english))
    return terms


def lexical_tokens(text: str, terms: list[tuple[str, str, str]] = ()) -> list[str]:
    text = normalize_search(text).lower()
    text = re.sub(r"^(?:query|passage):\s*", "", text)
    # Only remove separators between groups of three digits, not arbitrary commas.
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    tokens = [word for word in re.findall(r"[a-z]+(?:'[a-z]+)?", text) if word not in STOP_WORDS]
    for run in re.findall(f"{CJK}+", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            tokens.append(run)
    for match in re.finditer(NUMBER + r"\s*(%|percent\b)?", text):
        number = format(
            Decimal(match.group().rstrip().rstrip("%").replace("percent", "").strip()).normalize(),
            "f",
        )
        tokens.append(f"number:{number}")
        if match.group(1):
            tokens.append(f"percent:{number}")
    for spelling, currency in CURRENCY.items():
        if spelling in text:
            tokens.append(f"currency:{currency}")
        # Tie numbers to a currency too: prevents USD40000 matching HKD40000 equally.
        escaped = re.escape(spelling)
        patterns = [escaped + r"\s*(" + NUMBER + ")", "(" + NUMBER + r")\s*" + escaped]
        for pattern in patterns:
            for amount in re.findall(pattern, text):
                tokens.append(f"amount:{currency}:{format(Decimal(amount).normalize(), 'f')}")
    for token, chinese, english in terms:
        if chinese in text or re.search(r"\b" + re.escape(english) + r"\b", text):
            tokens.append(token)
    return tokens
