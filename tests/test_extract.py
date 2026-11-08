from conftest import read_fixture

from seo_brief.extract import (
    bangla_ratio,
    classify_links,
    count_words,
    is_question,
    parse_html,
    tokenize,
)

# -- tokenisation ------------------------------------------------------


def test_tokenize_lowercases_and_splits():
    assert tokenize("Hello, World! 2026") == ["hello", "world", "2026"]


def test_tokenize_keeps_apostrophes():
    assert tokenize("don't stop") == ["don't", "stop"]


def test_tokenize_bangla_keeps_vowel_signs():
    assert tokenize("ইমেইল মার্কেটিং") == ["ইমেইল", "মার্কেটিং"]


def test_count_words_mixed_scripts():
    assert count_words("SEO মানে search engine optimization") == 5


def test_bangla_ratio_detects_script():
    assert bangla_ratio("ইমেইল মার্কেটিং") > 0.9
    assert bangla_ratio("plain english") == 0.0
    assert bangla_ratio("") == 0.0


def test_is_question_variants():
    assert is_question("What is SEO?")
    assert is_question("What is SEO?  ")
    assert is_question("কেন দরকার?")
    assert is_question("Why？")
    assert not is_question("What is SEO")


# -- page metadata -------------------------------------------------------


def test_title_description_lang(page_a):
    assert page_a.title.startswith("Email Marketing for Small Business")
    assert "list building" in page_a.meta_description
    assert page_a.lang == "en"


def test_canonical(page_a, page_b):
    assert page_a.canonical == "https://www.example-a.test/email-marketing-small-business/"
    assert page_b.canonical.startswith("https://example-b.test")


def test_missing_meta_is_empty(page_c):
    assert page_c.meta_description == ""


def test_bangla_lang_and_title(page_bn):
    assert page_bn.lang == "bn"
    assert "ইমেইল" in page_bn.title


# -- headings ------------------------------------------------------------


def test_h1_found(page_a):
    assert page_a.h1 == ["Email Marketing for Small Business"]


def test_headings_levels_h1_to_h3_only(page_a):
    levels = {h.level for h in page_a.headings}
    assert levels <= {1, 2, 3}
    assert 3 in levels


def test_h3_captured(page_a):
    assert any(h.level == 3 and h.text == "Lead magnet ideas" for h in page_a.headings)


def test_footer_and_sidebar_headings_excluded(page_a):
    texts = [h.text for h in page_a.headings]
    assert "Subscribe to our newsletter" not in texts
    assert "Popular posts" not in texts


def test_comments_block_excluded(page_b):
    assert "Comments" not in [h.text for h in page_b.headings]
    assert "Great post" not in page_b.main_text


# -- questions -----------------------------------------------------------


def test_questions_from_headings(page_a):
    assert "How often should you send marketing emails?" in page_a.questions
    assert "What is a good email open rate?" in page_a.questions


def test_questions_deduplicated_with_schema(page_a):
    count = page_a.questions.count("How often should you send marketing emails?")
    assert count == 1


def test_bangla_question_headings(page_bn):
    assert len(page_bn.questions) == 2
    assert all(q.endswith("?") for q in page_bn.questions)


def test_non_question_headings_not_listed(page_c):
    assert "How to build an email list" not in page_c.questions


# -- main content --------------------------------------------------------


def test_script_and_style_text_not_in_main(page_a):
    assert "tracking" not in page_a.main_text
    assert "color:red" not in page_a.main_text


def test_nav_not_in_main(page_a):
    assert "Contact" not in page_a.main_text


def test_word_count_reasonable(page_a, page_b, page_c):
    assert 300 < page_a.word_count < 420
    assert 250 < page_b.word_count < 380
    assert 150 < page_c.word_count < 280


def test_heuristic_without_article_tag(page_b, page_c):
    assert "welcome series" in page_b.main_text
    assert "Join our newsletter" not in page_c.main_text


def test_no_semantic_tags_fixture():
    page = parse_html(read_fixture("no_semantic.html"), "https://x.test/")
    assert "score paragraph blocks" in page.main_text
    assert "Three" not in page.main_text
    assert page.word_count > 60


def test_minimal_page_does_not_crash():
    page = parse_html(read_fixture("minimal.html"), "https://x.test/")
    assert page.title == "Tiny"
    assert page.word_count == 1
    assert page.headings == []


def test_empty_html():
    page = parse_html("", "https://x.test/")
    assert page.word_count == 0
    assert page.title == ""


def test_bangla_word_count(page_bn):
    assert 60 < page_bn.word_count < 140


# -- schema --------------------------------------------------------------


def test_schema_graph_types(page_a):
    assert {"Article", "BreadcrumbList", "FAQPage"} <= set(page_a.schema_types)


def test_schema_type_list(page_b):
    assert page_b.schema_types == ["Article", "BlogPosting"]


def test_invalid_jsonld_ignored_valid_kept(page_c):
    assert page_c.schema_types == ["Organization"]


def test_schema_question_names_merged(page_a):
    # the FAQPage question also appears as a heading, so it is not duplicated
    assert page_a.questions.count("How often should you send marketing emails?") == 1


# -- links and images ----------------------------------------------------


def test_link_counts_page_a(page_a):
    assert page_a.internal_links == 2
    assert page_a.external_links == 1


def test_link_counts_skip_mailto_anchor_js(page_b):
    # 1 absolute same-host link counted internal, protocol-relative CDN external
    assert page_b.internal_links == 1
    assert page_b.external_links == 1


def test_classify_links_relative_offline():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup('<a href="/a">a</a><a href="https://o.test/">o</a>', "html.parser")
    assert classify_links(soup, "file://page.html") == (1, 1)


def test_classify_links_www_equivalence():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup('<a href="https://www.site.test/x">x</a>', "html.parser")
    assert classify_links(soup, "https://site.test/") == (1, 0)


def test_images_and_alt_coverage(page_a, page_b):
    assert (page_a.images, page_a.images_with_alt) == (2, 1)
    assert page_a.alt_coverage == 0.5
    assert (page_b.images, page_b.images_with_alt) == (3, 2)


def test_alt_coverage_without_images_is_one(page_bn):
    page = parse_html("<html><body></body></html>", "https://x.test/")
    assert page.alt_coverage == 1.0
    assert page_bn.alt_coverage == 1.0


# -- eeat signals --------------------------------------------------------


def test_author_and_date_detection(page_a, page_b, page_c):
    assert page_a.has_author and page_a.has_date
    assert page_b.has_author and page_b.has_date
    assert not page_c.has_author and not page_c.has_date


def test_to_dict_contains_alt_coverage(page_a):
    data = page_a.to_dict()
    assert data["alt_coverage"] == 0.5
    assert data["headings"][0]["level"] == 1
