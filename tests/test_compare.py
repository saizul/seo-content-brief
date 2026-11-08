import json

from seo_brief.cli import main
from seo_brief.compare import compare_headings, compare_pages, compare_terms
from seo_brief.extract import Heading, PageData


def make_page(url, headings, text=""):
    page = PageData(url=url, main_text=text, word_count=len(text.split()))
    page.headings = [Heading(level, t) for level, t in headings]
    return page


def test_headings_are_matched_one_to_one():
    a = make_page("a", [(2, "Email list building tips"), (2, "Pricing"), (3, "Pricing plans")])
    b = make_page(
        "b", [(2, "Email list building tips and tricks"), (2, "Pricing plans"), (2, "Templates")]
    )
    result = compare_headings(a, b)
    pairs = {(s["a"], s["b"]) for s in result["shared"]}
    assert ("Email list building tips", "Email list building tips and tricks") in pairs
    assert ("Pricing plans", "Pricing plans") in pairs
    assert result["only_a"] == ["Pricing"]
    assert result["only_b"] == ["Templates"]
    assert result["overlap"] == 0.5  # 2 shared of 4 distinct


def test_question_headings_and_h1_are_ignored():
    a = make_page("a", [(1, "Title"), (2, "What is SEO?")])
    b = make_page("b", [(2, "Anything else")])
    result = compare_headings(a, b)
    assert result["shared"] == [] and result["only_a"] == []
    assert result["only_b"] == ["Anything else"]


def test_identical_outlines_have_full_overlap():
    heads = [(2, "Email automation basics"), (2, "Measuring campaign results")]
    result = compare_headings(make_page("a", heads), make_page("b", heads))
    assert result["overlap"] == 1.0 and not result["only_a"] and not result["only_b"]


def test_terms_split_into_shared_and_unique():
    a = make_page(
        "a",
        [],
        "Email automation saves time. Email automation scales. "
        "Segmentation helps. Segmentation wins.",
    )
    b = make_page(
        "b",
        [],
        "Email automation is key. Email automation again. "
        "Deliverability matters. Deliverability counts.",
    )
    terms = compare_terms(a, b)
    shared = {t["term"] for t in terms["shared"]}
    assert "email automation" in shared
    assert "segmentation" in {t["term"] for t in terms["only_a"]}
    assert "deliverability" in {t["term"] for t in terms["only_b"]}
    assert "segmentation" not in shared
    assert 0 < terms["overlap"] < 1


def test_single_occurrence_terms_are_ignored():
    a = make_page("a", [], "Rareword appears once. Common common.")
    b = make_page("b", [], "Other text here. Common common.")
    terms = compare_terms(a, b)
    assert "rareword" not in {t["term"] for t in terms["only_a"]}


def test_compare_pages_reports_stats():
    a = make_page("a", [(2, "One")], "alpha beta gamma")
    b = make_page("b", [], "alpha")
    result = compare_pages(a, b)
    assert result["a"]["words"] == 3 and result["b"]["words"] == 1
    assert result["a"]["headings"] == 1 and result["b"]["headings"] == 0


def test_cli_compare_json_with_local_files(fixtures_dir, capsys):
    code = main(
        [
            "compare",
            str(fixtures_dir / "guide_a.html"),
            str(fixtures_dir / "guide_b.html"),
            "--json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["a"]["url"] == "guide_a.html" and data["b"]["url"] == "guide_b.html"
    assert data["a"]["words"] > 0
    assert data["headings"]["shared"] or data["terms"]["shared"]


def test_cli_compare_table_output(fixtures_dir, capsys):
    code = main(["compare", str(fixtures_dir / "guide_a.html"), str(fixtures_dir / "guide_c.html")])
    assert code == 0
    out = capsys.readouterr().out
    assert "Heading overlap" in out and "Term overlap" in out


def test_cli_compare_missing_file(fixtures_dir, tmp_path):
    assert main(["compare", str(fixtures_dir / "guide_a.html"), str(tmp_path / "nope.html")]) == 2


def test_cli_compare_rejects_bad_top(fixtures_dir):
    path = str(fixtures_dir / "guide_a.html")
    assert main(["compare", path, path, "--top", "0"]) == 2
