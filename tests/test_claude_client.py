import json
from pathlib import Path

from comms_bot.claude_client import FALLBACK_TEXT, AnswerEngine, load_faq, normalise
from comms_bot.config import Settings

PAIRS = [
    {"question": "What are your opening hours?", "answer": "Mon-Fri 8-18."},
    {"question": "Do you offer emergency call-outs?", "answer": "Yes, 24/7."},
]


def make_engine(tmp_path: Path, api_key: str = "") -> AnswerEngine:
    faq_file = tmp_path / "faq.json"
    faq_file.write_text(json.dumps(PAIRS), encoding="utf-8")
    settings = Settings(
        _env_file=None,
        anthropic_api_key=api_key,
        faq_file=str(faq_file),
        outbox_dir=str(tmp_path / "outbox"),
        database_url=f"sqlite:///{tmp_path}/test.db",
    )
    return AnswerEngine(settings)


def test_normalise_strips_punctuation_and_case():
    assert normalise("  What ARE your opening-hours?! ") == "what are your opening hours"


def test_load_faq_missing_file_returns_empty(tmp_path):
    assert load_faq(str(tmp_path / "missing.json")) == []


def test_exact_question_matches_faq(tmp_path):
    engine = make_engine(tmp_path)
    reply = engine.answer("What are your opening hours?")
    assert reply.source == "faq"
    assert reply.text == "Mon-Fri 8-18."
    assert reply.matched_question == "What are your opening hours?"


def test_partial_phrasing_matches_faq(tmp_path):
    engine = make_engine(tmp_path)
    # token_set_ratio scores token subsets at 100, so terser phrasings match
    reply = engine.answer("opening hours?")
    assert reply.source == "faq"
    assert reply.matched_question == "What are your opening hours?"


def test_unrelated_question_falls_back_without_api_key(tmp_path):
    engine = make_engine(tmp_path)
    reply = engine.answer("Can I bring my dog to the showroom?")
    assert reply.source == "fallback"
    assert reply.text == FALLBACK_TEXT


def test_llm_fallback_is_cached(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, api_key="test-key")
    calls: list[str] = []

    def fake_ask(question: str) -> str:
        calls.append(question)
        return "You can pay in three instalments."

    monkeypatch.setattr(engine, "_ask_claude", fake_ask)

    first = engine.answer("Can I pay in instalments?")
    assert first.source == "llm"
    assert first.text == "You can pay in three instalments."

    second = engine.answer("Can I pay in instalments?")
    assert second.source == "cache"
    assert second.text == first.text
    assert len(calls) == 1  # the repeat never reached the API


def test_failed_llm_call_falls_back(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, api_key="test-key")
    monkeypatch.setattr(engine, "_ask_claude", lambda question: None)
    reply = engine.answer("Can I pay in instalments?")
    assert reply.source == "fallback"


def test_reload_clears_cache(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, api_key="test-key")
    calls: list[str] = []

    def fake_ask(question: str) -> str:
        calls.append(question)
        return "LLM answer"

    monkeypatch.setattr(engine, "_ask_claude", fake_ask)
    engine.answer("Can I pay in instalments?")
    engine.reload()
    engine.answer("Can I pay in instalments?")
    assert len(calls) == 2
