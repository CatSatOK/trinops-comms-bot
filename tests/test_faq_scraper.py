import json
from pathlib import Path

from comms_bot.faq_scraper import parse_faq, scrape_to_file

DETAILS_HTML = """
<html><body>
<details><summary>What are your opening hours?</summary><p>Mon-Fri 8-18.</p></details>
<details><summary>Do you deliver?</summary><p>Yes, nationwide.</p></details>
<details><p>An accordion without a summary is skipped.</p></details>
</body></html>
"""

HEADINGS_HTML = """
<html><body>
<h2>Help centre</h2>
<h3>What is your cancellation policy?</h3>
<p>Free up to 24 hours before.</p>
<p>Later cancellations cost 50%.</p>
<h3>Our awards</h3>
<p>Not a question, so not extracted.</p>
<h3>Do you provide a warranty?</h3>
<ul><li>12 months parts and labour.</li></ul>
</body></html>
"""

DL_HTML = """
<html><body>
<dl>
  <dt>What payment methods do you accept?</dt>
  <dd>Cards and bank transfer.</dd>
  <dt>Orphan question with no dd</dt>
</dl>
</body></html>
"""


def test_parse_details_accordions():
    pairs = parse_faq(DETAILS_HTML)
    assert [p.question for p in pairs] == [
        "What are your opening hours?",
        "Do you deliver?",
    ]
    assert pairs[0].answer == "Mon-Fri 8-18."


def test_parse_question_headings():
    pairs = parse_faq(HEADINGS_HTML)
    assert [p.question for p in pairs] == [
        "What is your cancellation policy?",
        "Do you provide a warranty?",
    ]
    # consecutive paragraphs are joined into one answer
    assert pairs[0].answer == "Free up to 24 hours before. Later cancellations cost 50%."


def test_parse_definition_lists():
    pairs = parse_faq(DL_HTML)
    assert len(pairs) == 1
    assert pairs[0].question == "What payment methods do you accept?"
    assert pairs[0].answer == "Cards and bank transfer."


def test_duplicate_questions_are_deduped():
    html = (
        "<details><summary>Do you deliver?</summary><p>Yes.</p></details>"
        "<h3>Do you deliver?</h3><p>Yes we do.</p>"
    )
    pairs = parse_faq(html)
    assert len(pairs) == 1
    assert pairs[0].answer == "Yes."  # first strategy wins


def test_scrape_to_file_writes_json(tmp_path):
    source = tmp_path / "faq.html"
    source.write_text(DETAILS_HTML, encoding="utf-8")
    output = tmp_path / "out" / "faq.json"

    count = scrape_to_file(str(source), str(output))

    assert count == 2
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data[1] == {"question": "Do you deliver?", "answer": "Yes, nationwide."}


def test_bundled_demo_faq_page_parses():
    """The demo knowledge base comes from the real scraper run on this page."""
    html = Path("demo/faq-page.html").read_text(encoding="utf-8")
    pairs = parse_faq(html)
    questions = [p.question for p in pairs]
    assert len(pairs) == 10
    assert "What are your opening hours?" in questions  # details strategy
    assert "What is your cancellation policy?" in questions  # heading strategy
