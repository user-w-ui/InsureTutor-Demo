"""The chat lifecycle: mandatory retrieval, bounded Agent, local checks, fallback."""

from __future__ import annotations

import asyncio
import json
import re

from opencc import OpenCC

from insuretutor.agent_tools import EvidenceSearchSession
from insuretutor.chat_models import ChatResult, ChatTurn
from insuretutor.generation import AgentGenerator, FormatFailure
from insuretutor.guardrails.answers import (
    AnswerRejected,
    EvidenceRegistry,
    message,
    validate_answer,
)
from insuretutor.retrieval import Retriever
from insuretutor.sessions import HistoryTurn, SessionStore


def response_language(question: str, requested: str) -> str:
    if requested != "auto":
        return requested
    if not re.search(r"[\u3400-\u9fff]", question):
        return "en"
    return "zh-Hant" if OpenCC("t2s").convert(question) != question else "zh-Hans"


class Tutor:
    def __init__(
        self,
        retriever: Retriever,
        generator: AgentGenerator | None = None,
        *,
        sessions: SessionStore | None = None,
        timeout: float = 60,
    ):
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        self.retriever, self.generator = retriever, generator
        self.sessions, self.timeout = sessions or SessionStore(), timeout

    async def answer(self, turn: ChatTurn) -> ChatResult:
        language = response_language(turn.question, turn.response_language)
        async with self.sessions.use(turn.session_id) as (conversation, reset):
            search = EvidenceSearchSession(self.retriever, response_language=language)
            calls = [0]
            try:
                async with asyncio.timeout(self.timeout):
                    initial = await search.initialize(turn.question)
                    if self.generator is None:
                        result = self._fallback(
                            search, conversation.id, language, "model_unconfigured"
                        )
                    else:
                        data = {
                            "question": turn.question,
                            "response_language": language,
                            "history": [h.as_data() for h in conversation.history],
                            "initial_evidence": json.loads(initial.to_agent_json()),
                            "limits": {
                                "remaining_searches": initial.remaining_searches,
                                "remaining_source_characters": initial.remaining_source_characters,
                            },
                        }
                        draft = await self.generator.generate(data, search, calls)
                        registry = EvidenceRegistry(search)
                        draft = validate_answer(
                            draft,
                            registry,
                            [h.question for h in conversation.history] + [turn.question],
                            language,
                        )
                        ids = list(
                            dict.fromkeys(uid for c in draft.claims for uid in c.evidence_ids)
                        )
                        citations = registry.citations(ids, language)
                        if not registry.units:
                            result = self._fallback(
                                search, conversation.id, language, "no_evidence"
                            )
                        else:
                            used = registry.closure(ids)
                            conflict = any(
                                registry.units[u].conflict or u in registry.conflicts for u in used
                            )
                            explanation = "\n\n".join(c.text for c in draft.claims)
                            if not explanation:
                                explanation = message(
                                    "insufficient" if draft.status == "insufficient" else "scope",
                                    language,
                                )
                            notices = [message("conflict", language)] if conflict else []
                            if any(c.calculation for c in draft.claims):
                                notices.append(message("calculation", language))
                            result = ChatResult(
                                session_id=conversation.id,
                                response_language=language,
                                status="source_conflict" if conflict else draft.status,
                                explanation=explanation,
                                claims=draft.claims,
                                citations=citations,
                                clarification_question=draft.clarification_question,
                                notices=notices,
                            )
            except TimeoutError:
                result = self._fallback(search, conversation.id, language, "timeout")
            except AnswerRejected as exc:
                result = self._fallback(search, conversation.id, language, str(exc))
            except FormatFailure:
                result = self._fallback(search, conversation.id, language, "invalid_json")
            except Exception as exc:  # noqa: BLE001 -- isolate provider/tool failures at chat boundary
                # Exception text may contain keys, prompts or source bodies. Only
                # coarse server-owned reasons are returned; no payload logging.
                reason = (
                    "retrieval_failed" if search.initial_result is None else "model_or_tool_failed"
                )
                if type(exc).__name__ == "MaxTurnsExceeded":
                    reason = "turn_limit"
                result = self._fallback(search, conversation.id, language, reason)
            result.searches, result.model_calls, result.context_reset = (
                search.calls,
                calls[0],
                reset,
            )
            if reset:
                result.notices.insert(0, message("reset", language))
            # Excerpts and failures are not validated conversational answers.
            if result.reason is None:
                registry = EvidenceRegistry(search)
                topics = sorted(
                    {
                        registry.units[u].evidence_group
                        for c in result.claims
                        for u in c.evidence_ids
                    }
                )
                completed_text = "\n".join(
                    [result.explanation, *result.notices, result.clarification_question or ""]
                )
                self.sessions.complete(
                    conversation, HistoryTurn(turn.question, completed_text, topics)
                )
            return result

    @staticmethod
    def _fallback(search, session_id: str, language: str, reason: str) -> ChatResult:
        registry = EvidenceRegistry(search)
        # All already-delivered sources, in retrieval order, with complete notes;
        # no partial generated claims survive a failure.
        ids = list(dict.fromkeys(u for b in search.bundles for u in b.selected_unit_ids))
        if not ids:
            ids = list(registry.units)
        try:
            citations = registry.citations(ids, language)
        except AnswerRejected:
            citations = []
        return ChatResult(
            session_id=session_id,
            response_language=language,
            status="excerpts" if citations else "insufficient",
            reason=reason,
            explanation=message("excerpts" if citations else "insufficient", language),
            citations=citations,
            notices=[message("conflict", language)]
            if citations and any(registry.units[u].conflict for u in registry.closure(ids))
            else [],
        )
