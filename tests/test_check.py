import json

import pytest

from seo_brief.analyze import OutlineItem, TermStat, WordCountAdvice
from seo_brief.brief import build_brief
from seo_brief.check import (
    check_draft,
    check_keyword,
    check_outline,
    check_questions,
    check_terms,
    check_word_count,
    grade,
    parse_markdown,
)
from seo_brief.cli import main
from seo_brief.extract import Heading, PageData

KEYWORD = "email marketing for small business"

DRAFT_MD = """---
title: "Email marketing for small business: a starter guide"
draft: true
---
# Email marketing for small business

Email marketing for small business owners is the cheapest channel you control.
![Open rate chart](chart.png) ![](decorative.png)

## How to build an email list
Use a lead magnet and a [signup form](https://example.test/form).

```
## not a heading inside a code fence
```

## Email automation workflows
Welcome series and abandoned cart emails save time.

### How often should you send marketing emails?
Once a week is a good start.
"""


def make_draft(headings=(), text="", title=""):
    page = PageData(url="draft", title=title, main_text=text, word_count=len(text.split()))
    page.headings = [Heading(level, t) for level, t in headings]
    page.h1 = [t for level, t in headings if level == 1]
    return page


# --- Markdown parsing -------------------------------------------------------


def test_parse_markdown_structure():
    page = parse_markdown(DRAFT_MD, "draft.md")
    assert page.title == "Email marketing for small business: a starter guide"
    assert page.h1 == ["Email marketing for small business"]
    levels = [(h.level, h.text) for h in page.headings]
    assert (2, "How to build an email list") in levels
    assert (3, "How often should you send marketing emails?") in levels
    assert not any("code fence" in h.text for h in page.headings)
    assert page.questions == ["How often should you send marketing emails?"]
    assert page.images == 2 and page.images_with_alt == 1
    assert "signup form" in page.main_text and "https://" not in page.main_text
    assert "draft: true" not in page.main_text
    assert page.word_count > 30


def test_parse_markdown_title_falls_back_to_h1():
    page = parse_markdown("# My title #\n\nSome **bold** text.", "x.md")
    assert page.title == "My title"
    assert "bold" in page.main_text and "*" not in page.main_text


# --- components -------------------------------------------------------------


def test_outline_coverage_uses_heading_similarity():
    outline = [
        OutlineItem("Email segmentation basics", 2, 3, 0.2),
        OutlineItem("Measuring email campaign results", 2, 2, 0.8),
    ]
    draft = make_draft([(2, "Segmentation basics for email"), (2, "Pricing")])
    result = check_outline(draft, outline)
    assert [c["section"] for c in result["covered"]] == ["Email segmentation basics"]
    assert result["missing"] == [{"section": "Measuring email campaign results", "pages": 2}]
    assert result["ratio"] == 0.5


def test_outline_empty_brief_is_not_applicable():
    assert check_outline(make_draft([(2, "Anything")]), [])["ratio"] is None


def test_questions_answered_by_heading():
    questions = [("What is a good email open rate?", 3), ("Is email marketing dead?", 1)]
    draft = make_draft([(2, "What is a good open rate for email?")])
    result = check_questions(draft, questions)
    assert result["answered"][0]["question"] == "What is a good email open rate?"
    assert result["unanswered"] == [{"question": "Is email marketing dead?", "pages": 1}]
    assert result["ratio"] == 0.5


def test_terms_match_plural_and_phrase_boundaries():
    terms = [TermStat("open rates", 3, 9, 1.0), TermStat("email list", 2, 5, 0.8),
             TermStat("deliverability", 2, 4, 0.5)]  # fmt: skip
    draft = make_draft(text="Your open rate matters. Grow the email lists. Email, list.")
    result = check_terms(draft, terms)
    assert {t["term"] for t in result["used"]} == {"open rates", "email list"}
    assert [t["term"] for t in result["missing"]] == ["deliverability"]


def test_terms_respect_top_limit():
    terms = [TermStat(f"term{i}", 2, 2, 1.0) for i in range(30)]
    result = check_terms(make_draft(text="nothing here"), terms, top=5)
    assert len(result["missing"]) == 5 and result["ratio"] == 0.0


@pytest.mark.parametrize(
    "words, status, ratio",
    [
        (100, "short", 0.5),
        (250, "ok", 1.0),
        (300, "ok", 1.0),
        (330, "long", 0.9),
        (450, "long", 0.5),
    ],
)
def test_word_count_scoring(words, status, ratio):
    advice = WordCountAdvice(low=200, high=300, target=250, median=250, samples=4)
    result = check_word_count(make_draft(text="w " * words), advice)
    assert result["status"] == status
    assert result["ratio"] == pytest.approx(ratio)


def test_word_count_without_advice():
    assert check_word_count(make_draft(text="a b"), None)["ratio"] is None


def test_keyword_placement():
    draft = make_draft(
        [(1, "Email marketing for small business owners"), (2, "Tools")],
        text="A guide to email marketing for a small business.",
        title="Small business email marketing",
    )
    result = check_keyword(draft, KEYWORD)
    assert result["places"] == {"title": True, "h1": True, "intro": True, "subheading": False}
    assert result["ratio"] == 0.75


def test_keyword_intro_only_counts_first_words():
    text = "filler " * 150 + "email marketing small business"
    result = check_keyword(make_draft(text=text), KEYWORD)
    assert result["places"]["intro"] is False


@pytest.mark.parametrize("score, letter", [(95, "A"), (75, "B"), (60.0, "C"), (45, "D"), (3, "F")])
def test_grade(score, letter):
    assert grade(score) == letter


# --- full check -------------------------------------------------------------


@pytest.fixture()
def brief(english_pages):
    return build_brief(KEYWORD, english_pages)


def test_competitor_page_scores_well_against_its_own_brief(brief, page_a):
    result = check_draft(page_a, brief)
    assert result["score"] >= 75
    assert result["outline"]["ratio"] == 1.0
    assert set(result["components"]) == {
        "outline", "terms", "questions", "word_count", "keyword_placement"
    }  # fmt: skip


def test_thin_draft_scores_low_with_suggestions(brief):
    draft = make_draft([(1, "Hello")], text="Short note.", title="Hello")
    result = check_draft(draft, brief)
    assert result["score"] < 20 and result["grade"] == "F"
    text = " ".join(result["suggestions"])
    assert "Expand the draft" in text
    assert "Add sections competitors cover" in text
    assert "Use the keyword" in text


def test_not_applicable_components_are_rescaled(page_a):
    stripped = PageData(url="c", main_text=page_a.main_text, word_count=page_a.word_count)
    brief = build_brief(KEYWORD, [stripped])
    result = check_draft(stripped, brief)
    assert result["components"]["questions"] is None
    assert result["components"]["outline"] is None
    assert 0 <= result["score"] <= 100


# --- CLI --------------------------------------------------------------------


def test_cli_check_json(tmp_path, fixtures_dir, capsys):
    draft = tmp_path / "draft.md"
    draft.write_text(DRAFT_MD, encoding="utf-8")
    code = main(["check", str(draft), "-k", KEYWORD, "--offline", str(fixtures_dir), "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["keyword"] == KEYWORD
    assert data["draft"]["url"] == "draft.md"
    assert 0 < data["score"] < 100
    assert data["keyword_placement"]["places"]["h1"] is True


def test_cli_check_min_score_fails(tmp_path, fixtures_dir, capsys):
    draft = tmp_path / "draft.md"
    draft.write_text(DRAFT_MD, encoding="utf-8")
    args = ["check", str(draft), "-k", KEYWORD, "--offline", str(fixtures_dir)]
    assert main(args + ["--min-score", "99"]) == 1
    out = capsys.readouterr().out
    assert "below --min-score" in out and "Next steps" in out
    assert main(args + ["--min-score", "1"]) == 0


def test_cli_check_html_draft(fixtures_dir, capsys):
    draft = fixtures_dir / "guide_a.html"
    code = main(["check", str(draft), "-k", KEYWORD, "--offline", str(fixtures_dir)])
    assert code == 0
    assert "Score breakdown" in capsys.readouterr().out


def test_cli_check_missing_draft(tmp_path, fixtures_dir):
    missing = tmp_path / "nope.md"
    assert main(["check", str(missing), "-k", KEYWORD, "--offline", str(fixtures_dir)]) == 2


def test_cli_check_empty_draft(tmp_path, fixtures_dir):
    empty = tmp_path / "empty.md"
    empty.write_text("---\ntitle: x\n---\n", encoding="utf-8")
    assert main(["check", str(empty), "-k", KEYWORD, "--offline", str(fixtures_dir)]) == 2


def test_cli_check_rejects_bad_top_terms(tmp_path, fixtures_dir):
    draft = tmp_path / "draft.md"
    draft.write_text(DRAFT_MD, encoding="utf-8")
    args = ["check", str(draft), "-k", KEYWORD, "--offline", str(fixtures_dir), "--top-terms", "0"]
    assert main(args) == 2
