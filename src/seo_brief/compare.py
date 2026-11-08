"""Head-to-head comparison of two pages: shared and unique headings and terms."""

from __future__ import annotations

from .analyze import _is_subphrase, _jaccard, heading_key, ngrams_in_text
from .extract import is_question

HEADING_THRESHOLD = 0.6


def _outline(page) -> list:
    return [h for h in page.headings if h.level in (2, 3) and not is_question(h.text)]


def compare_headings(a, b, threshold: float = HEADING_THRESHOLD) -> dict:
    """Match H2/H3 headings one-to-one by stemmed-word overlap (Jaccard >= threshold)."""
    heads_a, heads_b = _outline(a), _outline(b)
    keys_b = [heading_key(h.text) for h in heads_b]
    used: set = set()
    shared, only_a = [], []
    for ha in heads_a:
        key = heading_key(ha.text)
        best, best_sim = None, 0.0
        for j, kb in enumerate(keys_b):
            if j in used:
                continue
            sim = _jaccard(key, kb)
            if sim >= threshold and sim > best_sim:
                best, best_sim = j, sim
        if best is None:
            only_a.append(ha.text)
        else:
            used.add(best)
            shared.append({"a": ha.text, "b": heads_b[best].text, "similarity": round(best_sim, 2)})
    only_b = [h.text for j, h in enumerate(heads_b) if j not in used]
    union = len(shared) + len(only_a) + len(only_b)
    return {
        "shared": shared,
        "only_a": only_a,
        "only_b": only_b,
        "overlap": round(len(shared) / union, 3) if union else 0.0,
    }


def _term_counts(page, min_count: int) -> dict:
    counts = ngrams_in_text(page.main_text)
    kept = {t: n for t, n in counts.items() if n >= min_count}
    # A phrase that only ever occurs inside a longer phrase adds no information.
    return {
        t: n
        for t, n in kept.items()
        if not any(_is_subphrase(t, other) and kept[other] >= n for other in kept)
    }


def compare_terms(a, b, top: int = 15, min_count: int = 2) -> dict:
    """Terms (1-3 word phrases) used at least ``min_count`` times, split into shared / unique."""
    ta, tb = _term_counts(a, min_count), _term_counts(b, min_count)
    both = set(ta) & set(tb)
    shared = sorted(both, key=lambda t: (-(ta[t] + tb[t]), t))[:top]
    only_a = sorted(set(ta) - both, key=lambda t: (-ta[t], t))[:top]
    only_b = sorted(set(tb) - both, key=lambda t: (-tb[t], t))[:top]
    return {
        "shared": [{"term": t, "a": ta[t], "b": tb[t]} for t in shared],
        "only_a": [{"term": t, "count": ta[t]} for t in only_a],
        "only_b": [{"term": t, "count": tb[t]} for t in only_b],
        "overlap": round(_jaccard(frozenset(ta), frozenset(tb)), 3),
    }


def _stats(page) -> dict:
    return {
        "url": page.url,
        "title": page.title,
        "words": page.word_count,
        "headings": len(_outline(page)),
        "questions": len(page.questions),
        "internal_links": page.internal_links,
        "external_links": page.external_links,
        "images": page.images,
        "schema_types": list(page.schema_types),
    }


def compare_pages(a, b, top: int = 15) -> dict:
    return {
        "a": _stats(a),
        "b": _stats(b),
        "headings": compare_headings(a, b),
        "terms": compare_terms(a, b, top=top),
    }
