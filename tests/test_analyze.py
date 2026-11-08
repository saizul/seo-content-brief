import pytest

from seo_brief.analyze import (
    analyze_pages,
    collect_questions,
    heading_key,
    merge_outline,
    min_doc_freq,
    ngrams_in_text,
    page_text_stats,
    percentile,
    schema_summary,
    tfidf_terms,
    word_count_advice,
)
from seo_brief.extract import Heading, PageData
from seo_brief.stopwords import ALL, BANGLA, ENGLISH, is_stopword


def make_page(url, headings, questions=None, words=100):
    return PageData(
        url=url,
        headings=[Heading(lv, tx) for lv, tx in headings],
        questions=questions or [],
        word_count=words,
    )


# -- stopwords -----------------------------------------------------------


def test_stopwords_english_and_bangla():
    assert "the" in ENGLISH
    assert "এবং" in BANGLA
    assert is_stopword("and") and is_stopword("না")
    assert not is_stopword("email")
    assert ENGLISH <= ALL and BANGLA <= ALL


# -- n-grams -------------------------------------------------------------


def test_ngrams_exclude_stopwords():
    counts = ngrams_in_text("The email list is the best list", max_n=2)
    assert counts["email"] == 1
    assert counts["list"] == 2
    assert counts["email list"] == 1
    assert "the email" not in counts


def test_ngrams_do_not_cross_sentences():
    counts = ngrams_in_text("Email list. Marketing tools", max_n=2)
    assert "list marketing" not in counts
    assert counts["marketing tools"] == 1


def test_ngrams_bangla_sentence_boundary():
    counts = ngrams_in_text("ইমেইল লিস্ট। মার্কেটিং টুল", max_n=2)
    assert "ইমেইল লিস্ট" in counts
    assert "লিস্ট মার্কেটিং" not in counts


def test_ngrams_ignore_numbers_and_single_chars():
    counts = ngrams_in_text("2026 x seo", max_n=1)
    assert list(counts) == ["seo"]


# -- tf-idf --------------------------------------------------------------


def test_min_doc_freq_scales():
    assert min_doc_freq(1) == 1
    assert min_doc_freq(2) == 2
    assert min_doc_freq(3) == 2
    assert min_doc_freq(10) == 3


def test_tfidf_requires_shared_terms():
    texts = ["alpha beta gamma", "alpha delta", "alpha epsilon"]
    terms = {t.term for t in tfidf_terms(texts)}
    assert "alpha" in terms
    assert "beta" not in terms


def test_tfidf_empty_input():
    assert tfidf_terms([]) == []


def test_tfidf_single_document_allowed():
    terms = tfidf_terms(["Email segmentation improves open rate."])
    assert any("email segmentation" in t.term for t in terms)


def test_tfidf_doc_freq_and_counts():
    texts = ["seo seo audit", "seo tools", "audit tools"]
    stats = {t.term: t for t in tfidf_terms(texts, min_df=2)}
    assert stats["seo"].doc_freq == 2
    assert stats["seo"].total_count == 3


def test_tfidf_ranks_multiword_phrases(english_pages):
    terms = [t.term for t in tfidf_terms([p.main_text for p in english_pages], top=40)]
    assert any(t in terms for t in ("email segmentation", "email automation", "email list"))


def test_tfidf_removes_redundant_subphrases():
    texts = ["email automation workflow tips", "email automation workflow ideas"]
    terms = [t.term for t in tfidf_terms(texts, top=50)]
    assert "email automation workflow" in terms
    assert "email automation" not in terms


def test_tfidf_top_limit(english_pages):
    assert len(tfidf_terms([p.main_text for p in english_pages], top=5)) == 5


def test_tfidf_bangla_terms(page_bn):
    terms = [t.term for t in tfidf_terms([page_bn.main_text], top=20)]
    assert any("ইমেইল" in t for t in terms)
    assert "এবং" not in terms


# -- outline merging -----------------------------------------------------


def test_heading_key_stems_plurals():
    assert heading_key("Email Tools") == heading_key("email tool")


def test_heading_key_drops_stopwords():
    assert heading_key("How to build an email list") == frozenset({"build", "email", "list"})


def test_merge_outline_common_headings():
    a = make_page("a", [(2, "Why email marketing works"), (2, "Build an email list")])
    b = make_page("b", [(2, "Why email marketing works"), (2, "How to build an email list")])
    items = merge_outline([a, b])
    assert [i.pages for i in items] == [2, 2]


def test_merge_outline_drops_singletons_with_many_pages():
    a = make_page("a", [(2, "Common topic"), (2, "Unique to a")])
    b = make_page("b", [(2, "Common topic")])
    items = merge_outline([a, b])
    assert [i.text for i in items] == ["Common topic"]


def test_merge_outline_single_page_keeps_all():
    a = make_page("a", [(2, "Pricing plans"), (3, "Support options")])
    assert len(merge_outline([a])) == 2


def test_merge_outline_excludes_h1_and_questions():
    a = make_page("a", [(1, "Title"), (2, "Is it good?"), (2, "Real topic")])
    items = merge_outline([a])
    assert [i.text for i in items] == ["Real topic"]


def test_merge_outline_orders_by_position():
    a = make_page("a", [(2, "Alpha topic"), (2, "Beta topic")])
    b = make_page("b", [(2, "Alpha topic"), (2, "Beta topic")])
    assert [i.text for i in merge_outline([a, b])] == ["Alpha topic", "Beta topic"]


def test_merge_outline_level_is_mode():
    a = make_page("a", [(3, "Setup guide")])
    b = make_page("b", [(2, "Setup guide")])
    c = make_page("c", [(3, "Setup guide")])
    assert merge_outline([a, b, c])[0].level == 3


def test_merge_outline_max_items():
    heads = [(2, f"topic{i} word{i}") for i in range(30)]
    assert len(merge_outline([make_page("a", heads)], max_items=5)) == 5


def test_merge_outline_fixture_pages(page_a, page_b, page_c):
    items = merge_outline([page_a, page_b, page_c])
    texts = " ".join(i.text.lower() for i in items)
    assert "email list" in texts
    assert "segmentation" in texts


# -- word count ----------------------------------------------------------


def test_percentile_interpolates():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([5], 0.9) == 5.0


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_word_count_advice_none_for_empty():
    assert word_count_advice([]) is None
    assert word_count_advice([0, 0]) is None


def test_word_count_advice_single_page_band():
    adv = word_count_advice([1000])
    assert adv.low < 1000 < adv.high
    assert adv.samples == 1


def test_word_count_advice_rounded_to_50():
    adv = word_count_advice([1210, 1580, 1930, 2210, 2490])
    assert adv.low % 50 == 0 and adv.high % 50 == 0 and adv.target % 50 == 0
    assert adv.low <= adv.target <= adv.high


def test_word_count_advice_ignores_zero_pages():
    assert word_count_advice([0, 800]).samples == 1


def test_word_count_advice_identical_values_widen():
    adv = word_count_advice([500, 500, 500, 500])
    assert adv.high > adv.low


# -- questions / schema / stats -----------------------------------------


def test_collect_questions_counts_pages(page_a, page_c):
    result = dict(collect_questions([page_a, page_c]))
    assert result["How often should you send marketing emails?"] == 2


def test_collect_questions_case_insensitive():
    a = make_page("a", [], ["How Much Does It Cost?"])
    b = make_page("b", [], ["how much does it cost?"])
    assert collect_questions([a, b])[0][1] == 2


def test_collect_questions_limit():
    a = make_page("a", [], [f"Question number {i}?" for i in range(20)])
    assert len(collect_questions([a], limit=4)) == 4


def test_schema_summary_ignores_helper_types(page_a, page_b):
    summary = dict(schema_summary([page_a, page_b]))
    assert summary["Article"] == 2
    assert "Question" not in summary and "Answer" not in summary


def test_page_text_stats(page_a, page_b):
    st = page_text_stats([page_a, page_b])
    assert st["pages"] == 2
    assert st["with_author"] == 2
    assert 0 < st["alt_coverage"] < 1


def test_analyze_pages_keys(english_pages):
    result = analyze_pages(english_pages)
    assert set(result) == {"word_count", "outline", "questions", "terms", "schema", "stats"}
