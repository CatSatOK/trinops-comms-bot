"""FAQ page → knowledge base.

Point the scraper at the client's FAQ page (URL or local HTML file) and it
extracts Q&A pairs into `knowledge_base/faq.json`. Three parsing strategies
cover the common FAQ markups:

1. ``<details><summary>Question</summary>Answer</details>`` accordions
2. ``<dl>`` definition lists (``<dt>`` question, ``<dd>`` answer)
3. Question headings (h2–h5 ending in "?") followed by paragraphs/lists

Static HTML via httpx covers most sites. For JS-rendered FAQ pages install
playwright (optional, not in requirements.txt) and the scraper falls back to
a fully rendered page automatically when the static fetch finds nothing.

CLI: ``python -m comms_bot.faq_scraper <url-or-file> [output.json]``
"""

import json
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from comms_bot.claude_client import FaqEntry, normalise
from comms_bot.logging_conf import get_logger, setup_logging

logger = get_logger(__name__)

_HEADING_TAGS = ["h2", "h3", "h4", "h5"]


def fetch_html(source: str) -> str:
    if source.startswith(("http://", "https://")):
        response = httpx.get(source, follow_redirects=True, timeout=30)
        response.raise_for_status()
        return response.text
    return Path(source).read_text(encoding="utf-8")


def parse_faq(html: str) -> list[FaqEntry]:
    soup = BeautifulSoup(html, "html.parser")
    pairs = _from_details(soup) + _from_definition_lists(soup) + _from_headings(soup)

    seen: set[str] = set()
    unique: list[FaqEntry] = []
    for pair in pairs:
        key = normalise(pair.question)
        if pair.question and pair.answer and key not in seen:
            seen.add(key)
            unique.append(pair)
    return unique


def _clean(text: str) -> str:
    return " ".join(text.split())


def _from_details(soup: BeautifulSoup) -> list[FaqEntry]:
    pairs: list[FaqEntry] = []
    for details in soup.find_all("details"):
        summary = details.find("summary")
        if summary is None:
            continue
        question = _clean(summary.get_text())
        summary.extract()  # what remains in <details> is the answer
        answer = _clean(details.get_text(" "))
        if question and answer:
            pairs.append(FaqEntry(question=question, answer=answer))
    return pairs


def _from_definition_lists(soup: BeautifulSoup) -> list[FaqEntry]:
    pairs: list[FaqEntry] = []
    for dl in soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            question = _clean(dt.get_text())
            answer = _clean(dd.get_text(" "))
            if question and answer:
                pairs.append(FaqEntry(question=question, answer=answer))
    return pairs


def _from_headings(soup: BeautifulSoup) -> list[FaqEntry]:
    pairs: list[FaqEntry] = []
    for heading in soup.find_all(_HEADING_TAGS):
        question = _clean(heading.get_text())
        if not question.endswith("?"):
            continue
        parts: list[str] = []
        for sibling in heading.find_next_siblings():
            if not isinstance(sibling, Tag):
                continue
            if sibling.name in _HEADING_TAGS or sibling.name in ("details", "dl"):
                break
            if sibling.name in ("p", "ul", "ol"):
                parts.append(_clean(sibling.get_text(" ")))
        if parts:
            pairs.append(FaqEntry(question=question, answer=" ".join(parts)))
    return pairs


def _render_with_playwright(url: str) -> str | None:
    """Optional fallback for JS-heavy FAQ pages. Needs `pip install playwright`."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("playwright not installed — skipping rendered-page fallback")
        return None
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            return page.content()
        finally:
            browser.close()


def scrape_to_file(source: str, faq_file: str) -> int:
    html = fetch_html(source)
    pairs = parse_faq(html)
    if not pairs and source.startswith(("http://", "https://")):
        logger.info("static fetch found no Q&A pairs — trying a rendered page")
        rendered = _render_with_playwright(source)
        if rendered:
            pairs = parse_faq(rendered)

    path = Path(faq_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"question": p.question, "answer": p.answer} for p in pairs]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %d Q&A pairs from %s to %s", len(pairs), source, faq_file)
    return len(pairs)


def main() -> None:
    setup_logging()
    if len(sys.argv) < 2:
        print("usage: python -m comms_bot.faq_scraper <url-or-file> [output.json]")
        raise SystemExit(1)
    from comms_bot.config import get_settings

    output = sys.argv[2] if len(sys.argv) > 2 else get_settings().faq_file
    count = scrape_to_file(sys.argv[1], output)
    print(f"{count} Q&A pairs -> {output}")


if __name__ == "__main__":
    main()
