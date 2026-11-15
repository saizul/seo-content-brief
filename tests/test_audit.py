import json

import pytest

from seo_brief.audit import audit_html, fails, heading_skips, score
from seo_brief.cli import main

BODY = " ".join(["Plain words about email marketing for small business owners."] * 50)

DESCRIPTION = (
    "Learn email marketing for small business: build a list, segment subscribers and "
    "automate campaigns on a small budget."
)


GOOD = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Email marketing for small business: a starter guide</title>
<meta name="description" content="{DESCRIPTION}">
<link rel="canonical" href="https://example.test/email-marketing-small-business/">
<meta property="og:title" content="Email marketing">
<meta property="og:description" content="A starter guide">
<meta property="og:image" content="https://example.test/og.png">
<script type="application/ld+json">{{"@type": "Article"}}</script>
</head><body><article>
<h1>Email marketing for small business</h1>
<p>{BODY}</p>
<h2>Build a list</h2><p>{BODY}</p>
<h3>Lead magnets</h3><img src="a.png" alt="Chart"><img src="b.png" alt="">
</article></body></html>
"""

KEYWORD = "email marketing for small business"


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_clean_page_has_no_findings():
    result = audit_html(GOOD, "https://example.test/email-marketing-small-business/", KEYWORD)
    assert result["findings"] == []
    assert result["score"] == 100
    assert result["keyword"] == {"title": True, "h1": True, "description": True, "url": True}
    assert result["canonical"].endswith("/email-marketing-small-business/")
    assert result["word_count"] >= 300


def test_minimal_page_findings(fixtures_dir):
    html = (fixtures_dir / "minimal.html").read_text(encoding="utf-8")
    result = audit_html(html, "minimal.html")
    found = codes(result)
    assert {"h1-missing", "title-short", "description-missing", "lang-missing"} <= found
    assert {"viewport-missing", "thin-content", "canonical-missing", "open-graph-missing"} <= found
    assert result["counts"]["error"] == 1
    assert result["keyword"] is None
    # errors are listed first
    assert result["findings"][0]["severity"] == "error"


def test_title_and_description_length():
    html = GOOD.replace("Email marketing for small business: a starter guide", "x" * 70)
    html = html.replace(DESCRIPTION, "Too short")
    found = codes(audit_html(html, "page.html"))
    assert "title-long" in found
    assert "description-short" in found
    assert "description-long" in codes(audit_html(GOOD.replace(DESCRIPTION, "y " * 100), "p"))


def test_multiple_h1_and_heading_skip():
    html = GOOD.replace("<h3>Lead magnets</h3>", "<h1>Second</h1><h2>A</h2><h4>Deep</h4>")
    result = audit_html(html, "page.html")
    found = codes(result)
    assert "h1-multiple" in found
    assert "heading-skip" in found
    assert any("H2 to H4" in f["message"] for f in result["findings"])


def test_heading_skips_helper():
    assert heading_skips([1, 2, 3, 2, 3]) == []
    assert heading_skips([1, 3, 2, 5]) == [(1, 3), (2, 5)]
    assert heading_skips([]) == []


@pytest.mark.parametrize(
    "meta",
    [
        '<meta name="robots" content="noindex, follow">',
        '<meta name="ROBOTS" content="none">',
        '<meta name="googlebot" content="NOINDEX">',
    ],
)
def test_noindex_is_an_error(meta):
    result = audit_html(GOOD.replace("</head>", meta + "</head>"), "page.html")
    assert result["noindex"] is True
    assert "noindex" in codes(result)
    assert result["counts"]["error"] == 1


def test_robots_index_follow_is_fine():
    html = GOOD.replace("</head>", '<meta name="robots" content="index, follow"></head>')
    assert audit_html(html, "page.html")["noindex"] is False


def test_canonical_problems():
    relative = GOOD.replace("https://example.test/email-marketing-small-business/", "/relative/")
    assert "canonical-relative" in codes(audit_html(relative, "page.html"))

    cross = audit_html(GOOD, "https://other.test/post/")
    assert "canonical-cross-domain" in codes(cross)

    www = audit_html(GOOD, "https://www.example.test/post/")
    assert "canonical-cross-domain" not in codes(www)

    double = GOOD.replace(
        "</head>", '<link rel="canonical" href="https://example.test/other/"></head>'
    )
    assert "canonical-multiple" in codes(audit_html(double, "page.html"))


def test_invalid_jsonld_and_missing_alt():
    html = GOOD.replace('{"@type": "Article"}', '{"@type": "Article",}').replace(
        '<img src="b.png" alt="">', '<img src="b.png"><img src="c.png">'
    )
    result = audit_html(html, "page.html")
    found = codes(result)
    assert "jsonld-invalid" in found
    assert "img-alt-missing" in found
    assert any(f["message"].startswith("2 image(s)") for f in result["findings"])


def test_empty_alt_is_decorative_not_missing():
    assert "img-alt-missing" not in codes(audit_html(GOOD, "page.html"))


def test_keyword_placement_misses():
    result = audit_html(GOOD, "https://example.test/x/", "bangla seo tools")
    assert result["keyword"] == {"title": False, "h1": False, "description": False, "url": False}
    assert {"keyword-title", "keyword-h1", "keyword-description", "keyword-url"} <= codes(result)


def test_bangla_keyword():
    html = GOOD.replace("<h1>Email marketing for small business</h1>", "<h1>ইমেইল মার্কেটিং গাইড</h1>")
    result = audit_html(html, "page.html", "ইমেইল মার্কেটিং")
    assert result["keyword"]["h1"] is True
    assert result["keyword"]["title"] is False


def test_score_and_fail_on():
    assert score([]) == 100
    result = audit_html(GOOD.replace('<html lang="en">', "<html>"), "page.html")
    assert result["counts"] == {"error": 0, "warning": 1, "notice": 0}
    assert result["score"] == 95
    assert fails(result, None) is False
    assert fails(result, "error") is False
    assert fails(result, "warning") is True
    assert fails(result, "notice") is True


def test_score_floor_is_zero():
    assert audit_html("", "empty.html")["score"] >= 0


def test_cli_audit_json(tmp_path, capsys):
    path = tmp_path / "good.html"
    path.write_text(GOOD, encoding="utf-8")
    rc = main(["audit", str(path), "-k", KEYWORD, "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1 and data[0]["url"] == "good.html"
    assert data[0]["score"] == 100


def test_cli_audit_fail_on(fixtures_dir, capsys):
    minimal = str(fixtures_dir / "minimal.html")
    assert main(["audit", minimal, "--fail-on", "error"]) == 1
    assert "h1-missing" in capsys.readouterr().out
    good = str(fixtures_dir / "guide_a.html")
    assert main(["audit", good, "--fail-on", "error", "--json"]) == 0


def test_cli_audit_multiple_and_dedupe(fixtures_dir, capsys):
    a = str(fixtures_dir / "guide_a.html")
    b = str(fixtures_dir / "guide_b.html")
    assert main(["audit", a, b, a, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["url"] for d in data] == ["guide_a.html", "guide_b.html"]


def test_cli_audit_missing_file(tmp_path):
    assert main(["audit", str(tmp_path / "nope.html")]) == 2
