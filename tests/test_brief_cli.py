import datetime as dt
import json

import pytest

from seo_brief.brief import (
    build_brief,
    detect_language,
    eeat_checklist,
    render_html,
    render_markdown,
    suggest_schema,
)
from seo_brief.cli import build_parser, main, read_urls_file, slugify
from seo_brief.extract import PageData

TODAY = dt.date(2026, 3, 1)


@pytest.fixture()
def brief(english_pages):
    return build_brief("email marketing for small business", english_pages, today=TODAY)


def test_build_brief_requires_pages():
    with pytest.raises(ValueError):
        build_brief("kw", [])


def test_brief_metadata(brief):
    assert brief.generated == "2026-03-01"
    assert brief.language == "en"
    assert brief.skipped == []


def test_detect_language_bangla(page_bn):
    assert detect_language("ইমেইল মার্কেটিং", [page_bn]) == "bn"


def test_checklist_categories(brief):
    cats = {c for c, _ in brief.checklist}
    assert {"Experience", "Expertise", "Authoritativeness", "Trust"} <= cats


def test_checklist_uses_competitor_numbers(brief):
    text = " ".join(t for _, t in eeat_checklist(brief.analysis, "kw"))
    assert "2 of 3 competitors show an author" in text


def test_schema_suggestions_faq_when_questions(brief):
    assert any("FAQPage" in s for s in brief.schema_suggestions)


def test_schema_suggestions_no_questions():
    analysis = {"schema": [("Article", 1)], "questions": []}
    out = suggest_schema(analysis)
    assert out and not any("FAQPage" in s for s in out)


def test_markdown_sections(brief):
    md = render_markdown(brief)
    for heading in (
        "# Content brief: email marketing for small business",
        "## Recommended length",
        "## Suggested outline",
        "## Questions to answer",
        "## Terms to cover",
        "## E-E-A-T checklist",
        "## Competitor snapshot",
    ):
        assert heading in md


def test_markdown_contains_word_range_and_checkboxes(brief):
    md = render_markdown(brief)
    assert "Word count range:" in md
    assert "- [ ] " in md


def test_markdown_table_escapes_pipes(english_pages):
    page = PageData(url="https://x.test/a|b", main_text="word " * 50, word_count=50)
    md = render_markdown(build_brief("kw", [page], today=TODAY))
    assert "a\\|b" in md


def test_markdown_lists_skipped(english_pages):
    b = build_brief("kw", english_pages, skipped=[("https://z.test", "HTTP 404")], today=TODAY)
    md = render_markdown(b)
    assert "## Skipped URLs" in md and "HTTP 404" in md


def test_html_is_escaped_and_complete(english_pages):
    b = build_brief("<script>alert(1)</script>", english_pages, today=TODAY)
    html = render_html(b)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert html.startswith("<!DOCTYPE html>") and "</html>" in html


def test_html_has_checklist_inputs(brief):
    assert render_html(brief).count('type="checkbox"') == len(brief.checklist)


def test_html_bangla_lang(page_bn):
    b = build_brief("ইমেইল মার্কেটিং", [page_bn], today=TODAY)
    assert '<html lang="bn">' in render_html(b)


# -- cli -----------------------------------------------------------------


def test_slugify():
    assert slugify("Email Marketing, 2026!") == "email-marketing-2026"
    assert slugify("!!!") == "brief"
    assert slugify("ইমেইল মার্কেটিং").startswith("ইমেইল")


def test_read_urls_file_skips_comments(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# comment\nhttps://a.test/1\n\n  https://b.test/2  \n", encoding="utf-8")
    assert read_urls_file(f) == ["https://a.test/1", "https://b.test/2"]


def test_parser_requires_keyword():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["build"])


def test_cli_offline_build(fixtures_dir, tmp_path, capsys):
    out = tmp_path / "out"
    code = main(
        [
            "build",
            "-k",
            "email marketing",
            "--offline",
            str(fixtures_dir),
            "-o",
            str(out),
            "-f",
            "md,html,json",
        ]  # fmt: skip
    )
    assert code == 0
    assert (out / "email-marketing.md").read_text(encoding="utf-8").startswith("# Content brief")
    assert "<table>" in (out / "email-marketing.html").read_text(encoding="utf-8")
    data = json.loads((out / "email-marketing.json").read_text(encoding="utf-8"))
    assert len(data["pages"]) >= 6


def test_cli_offline_missing_dir(tmp_path):
    assert main(["build", "-k", "x", "--offline", str(tmp_path / "nope")]) == 2


def test_cli_offline_empty_dir(tmp_path):
    assert main(["build", "-k", "x", "--offline", str(tmp_path)]) == 2


def test_cli_no_sources_exits():
    with pytest.raises(SystemExit):
        main(["build", "-k", "x"])


def test_cli_analyze_json(fixtures_dir, capsys):
    code = main(["analyze", "-k", "x", "--offline", str(fixtures_dir), "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    urls = {p["url"] for p in data}
    assert "https://www.example-a.test/email-marketing-small-business/" in urls


def test_cli_analyze_table(fixtures_dir, capsys):
    assert main(["analyze", "-k", "x", "--offline", str(fixtures_dir)]) == 0
    assert "Competitors for" in capsys.readouterr().out
