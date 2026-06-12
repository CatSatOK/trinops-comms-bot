"""Answer engine.

Strategy: rapidfuzz match against the FAQ knowledge base first — free and
instant for close matches. Unmatched questions that were answered before come
from an in-memory cache. Only when both miss AND an Anthropic API key is
configured do we call claude-haiku (the cheapest Claude model), with the FAQ
injected as context. With no key configured the bot still works — unknown
questions get a polite fallback that points at escalation.
"""

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from rapidfuzz import fuzz, process

from comms_bot.config import Settings, get_settings
from comms_bot.logging_conf import get_logger

logger = get_logger(__name__)

FALLBACK_TEXT = (
    "I'm not sure about that one, sorry. Try rephrasing your question — "
    'or say "speak to someone" and I\'ll pass you over to the team.'
)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", text.lower())).strip()


@dataclass(frozen=True)
class FaqEntry:
    question: str
    answer: str


@dataclass(frozen=True)
class Reply:
    text: str
    source: str  # faq | cache | llm | fallback
    matched_question: str | None = None
    score: float | None = None


def load_faq(faq_file: str) -> list[FaqEntry]:
    path = Path(faq_file)
    if not path.exists():
        logger.warning("FAQ file %s missing — knowledge base is empty", faq_file)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [FaqEntry(question=d["question"], answer=d["answer"]) for d in data]


class AnswerEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._faq: list[FaqEntry] = []
        self._keys: list[str] = []
        self._cache: dict[str, Reply] = {}
        self.reload()

    @property
    def faq(self) -> list[FaqEntry]:
        return self._faq

    def reload(self) -> None:
        self._faq = load_faq(self._settings.faq_file)
        self._keys = [normalise(entry.question) for entry in self._faq]
        self._cache.clear()
        logger.info("knowledge base loaded: %d Q&A pairs", len(self._faq))

    def answer(self, question: str) -> Reply:
        key = normalise(question)

        matched = self._match(key)
        if matched is not None:
            return matched

        if key in self._cache:
            logger.info("cache hit for %r — no API call", key[:60])
            return replace(self._cache[key], source="cache")

        if self._settings.anthropic_api_key and self._faq:
            text = self._ask_claude(question)
            if text is not None:
                reply = Reply(text=text, source="llm")
                self._cache[key] = reply
                return reply

        return Reply(text=FALLBACK_TEXT, source="fallback")

    # --- rapidfuzz match — no API call -------------------------------------

    def _match(self, key: str) -> Reply | None:
        if not self._faq:
            return None
        best = process.extractOne(key, self._keys, scorer=fuzz.token_set_ratio)
        if best is None:
            return None
        _, score, index = best
        entry = self._faq[index]
        if score < self._settings.fuzzy_match_threshold:
            logger.info(
                "no FAQ match for %r (best %.0f: %r)", key[:60], score, entry.question
            )
            return None
        logger.info("FAQ match %.0f for %r -> %r", score, key[:60], entry.question)
        return Reply(
            text=entry.answer, source="faq", matched_question=entry.question, score=score
        )

    # --- Claude fallback -----------------------------------------------------

    _SYSTEM_PROMPT = (
        "You are the website chat assistant for {company}. Answer the visitor's "
        "question using ONLY the FAQ below. If the FAQ does not cover it, say you "
        "are not sure and suggest they ask to speak to someone. Keep replies under "
        "80 words, plain text, no markdown.\n\nFAQ:\n{context}"
    )

    def _ask_claude(self, question: str) -> str | None:
        try:
            import anthropic

            pairs = self._faq[: self._settings.llm_max_context_pairs]
            context = "\n\n".join(f"Q: {e.question}\nA: {e.answer}" for e in pairs)
            client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
            message = client.messages.create(
                model=self._settings.claude_model,
                max_tokens=300,
                system=self._SYSTEM_PROMPT.format(
                    company=self._settings.company_name, context=context
                ),
                messages=[{"role": "user", "content": question[:2000]}],
            )
            logger.info("claude fallback answered %r", question[:60])
            return message.content[0].text.strip()
        except Exception:
            logger.exception("Claude fallback failed for %r", question[:60])
            return None


_engine: AnswerEngine | None = None


def get_answer_engine() -> AnswerEngine:
    global _engine
    if _engine is None:
        _engine = AnswerEngine(get_settings())
    return _engine
