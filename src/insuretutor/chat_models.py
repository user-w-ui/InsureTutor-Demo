"""Small public chat contract and the locally validated model draft."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ResponseLanguage = Literal["auto", "en", "zh-Hans", "zh-Hant"]
Boundary = Literal["purchase", "returns", "eligibility", "scope", "insufficient"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatTurn(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    response_language: ResponseLanguage = "auto"

    @model_validator(mode="after")
    def nonblank(self):
        if not self.question.strip():
            raise ValueError("Question cannot be blank")
        return self


class CalculationInput(StrictModel):
    name: Literal["basic_sum_insured", "account_value", "withdrawals", "withdrawal_timing"]
    # Exact user text, never a model-supplied source excerpt.
    user_text: str = Field(min_length=1, max_length=1000)


class Calculation(StrictModel):
    formula_id: Literal["table-97-row-1", "table-97-row-2", "table-97-row-3"]
    formula_expression: str = Field(min_length=1, max_length=200)
    inputs: list[CalculationInput] = Field(min_length=2, max_length=8)
    steps: str = Field(min_length=1, max_length=2000)
    result: str = Field(min_length=1, max_length=300)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=24)
    kind: Literal["fact", "boundary", "calculation", "user_condition", "application"] = "fact"
    boundary: Boundary | None = None
    # Mark repeated user conditions so they cannot masquerade as brochure facts.
    user_inputs: list[str] = Field(default_factory=list, max_length=8)
    calculation: Calculation | None = None

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "boundary":
            if self.boundary is None or self.evidence_ids or self.calculation or self.user_inputs:
                raise ValueError("Boundary uses only a server-owned boundary code")
        elif self.kind == "user_condition":
            if (
                not self.user_inputs
                or self.evidence_ids
                or self.boundary is not None
                or self.calculation
            ):
                raise ValueError("User conditions contain only exact user inputs")
        elif self.kind == "application":
            if not self.user_inputs or self.boundary or self.calculation:
                raise ValueError("Condition application needs user conditions")
        elif self.boundary is not None or self.user_inputs:
            raise ValueError("Factual claims cannot contain boundary or user-condition fields")
        if (self.kind == "calculation") != (self.calculation is not None):
            raise ValueError("Calculation metadata must match claim kind")
        return self


class DraftAnswer(StrictModel):
    status: Literal["answered", "clarification", "refused", "insufficient"]
    claims: list[Claim] = Field(default_factory=list, max_length=16)
    clarification_question: str | None = Field(default=None, min_length=1, max_length=400)

    @model_validator(mode="after")
    def consistent(self):
        if self.status in {"answered", "clarification"} and not self.claims:
            raise ValueError("An answer needs claims")
        if self.status == "clarification" and not self.clarification_question:
            raise ValueError("Clarification status needs one question")
        return self


class Citation(StrictModel):
    unit_ids: list[str]
    span_id: str
    quote: str
    pdf_page: int
    language: Literal["en", "zh-Hant"]
    source_id: str
    source_url: str
    bbox_raw: list[int | float]
    text_origin: str
    origin_span_id: str | None = None
    origin_ranges: list[Any] = Field(default_factory=list)
    bbox_precision: str | None = None
    quality_flags: list[str] = Field(default_factory=list)


class ChatResult(StrictModel):
    session_id: str
    response_language: Literal["en", "zh-Hans", "zh-Hant"]
    status: Literal[
        "answered", "clarification", "refused", "insufficient", "source_conflict", "excerpts"
    ]
    explanation: str
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    clarification_question: str | None = None
    notices: list[str] = Field(default_factory=list)
    reason: str | None = None
    searches: int = 0
    model_calls: int = 0
    context_reset: bool = False
